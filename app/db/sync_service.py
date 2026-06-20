"""
Dual-DB Sync Service — Background sync between local SQLite and remote PostgreSQL.

Strategy: Write-Behind Cache
─────────────────────────────
- All API reads/writes go to local SQLite first (fast, zero-latency)
- Background task periodically pushes changes to remote PostgreSQL (Supabase)
- On startup, if local is empty (fresh Docker container), hydrate from remote
- On shutdown, final flush ensures no data loss

This pattern is commonly known as:
  • Write-Behind Cache / Write-Through Cache
  • Edge-to-Cloud Sync (PouchDB↔CouchDB, Firebase offline, Realm Sync)
  • CQRS with local materialised view
"""

from __future__ import annotations

import asyncio
import logging
import datetime as _dt
from typing import Type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import local_session_factory, remote_session_factory
from app.models.db_models import (
    Base,
    UserRow,
    AuthAccountRow,
    AgentRow,
    AgentRuntimeRow,
    ModelConnectionRow,
    QueryRow,
    ResponseRow,
    AgentJobRow,
)

logger = logging.getLogger("vizhi.sync")

# Tables to sync, ordered by dependency (parents first so FK constraints pass)
SYNC_TABLES: list[Type[Base]] = [
    UserRow,
    AuthAccountRow,
    AgentRow,
    AgentRuntimeRow,
    ModelConnectionRow,
    QueryRow,
    ResponseRow,
    AgentJobRow,
]


class SyncService:
    """
    Manages bidirectional sync between local SQLite and remote PostgreSQL.

    Lifecycle:
      1. hydrate_local_from_remote()  — on container startup
      2. start()                      — begins background sync loop
      3. stop()                       — final flush + cancel loop
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._sync_count: int = 0
        self._last_error: str | None = None

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """Check if remote database is configured and sync is enabled."""
        return (
            settings.sync_enabled
            and bool(settings.remote_database_url)
            and remote_session_factory is not None
        )

    @property
    def status(self) -> dict:
        """Return current sync status (useful for health endpoints)."""
        return {
            "configured": self.is_configured,
            "running": self._running,
            "sync_count": self._sync_count,
            "last_error": self._last_error,
        }

    # ── Startup: Hydrate local from remote ──────────────────────────

    async def hydrate_local_from_remote(self) -> None:
        """
        On container startup, if the local SQLite is empty,
        pull all data from remote PostgreSQL (Supabase).
        """
        if not self.is_configured:
            logger.info("Remote DB not configured — skipping hydration")
            return

        # Check if local DB already has data (use users table as proxy)
        async with local_session_factory() as local_db:
            result = await local_db.execute(select(func.count(UserRow.id)))
            local_count = result.scalar() or 0

        if local_count > 0:
            logger.info(
                f"Local DB already has {local_count} users — skipping hydration"
            )
            return

        logger.info("Local DB is empty — hydrating from remote...")

        try:
            async with remote_session_factory() as remote_db:
                async with local_session_factory() as local_db:
                    total_rows = 0
                    for model_class in SYNC_TABLES:
                        count = await self._copy_table(
                            source_db=remote_db,
                            target_db=local_db,
                            model_class=model_class,
                            direction="remote → local",
                        )
                        total_rows += count
                    await local_db.commit()

            logger.info(f"✅ Hydration complete — {total_rows} total rows pulled")
        except Exception as e:
            logger.error(f"❌ Hydration failed: {e}", exc_info=True)
            self._last_error = f"Hydration failed: {e}"

    # ── Background Sync Loop ────────────────────────────────────────

    async def start(self) -> None:
        """Start the background sync loop."""
        if not self.is_configured:
            logger.info("Remote sync disabled — running local-only mode")
            return

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info(
            f"🔄 Sync started (interval: {settings.sync_interval}s, "
            f"batch_size: {settings.sync_batch_size})"
        )

    async def stop(self) -> None:
        """Stop the sync loop and perform a final flush."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Final flush — push any remaining local data to remote
        if self.is_configured:
            logger.info("Performing final sync before shutdown...")
            try:
                await self._sync_all_tables()
                logger.info("✅ Final sync complete")
            except Exception as e:
                logger.error(f"❌ Final sync failed: {e}", exc_info=True)

    async def _sync_loop(self) -> None:
        """Periodically sync local changes to remote."""
        while self._running:
            try:
                await asyncio.sleep(settings.sync_interval)
                await self._sync_all_tables()
                self._sync_count += 1
                self._last_error = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync error: {e}", exc_info=True)
                self._last_error = str(e)
                # Don't crash the loop — wait and retry
                await asyncio.sleep(5)

    # ── Core Sync Logic ─────────────────────────────────────────────

    async def _sync_all_tables(self) -> None:
        """Push all local data to remote for each table."""
        async with local_session_factory() as local_db:
            async with remote_session_factory() as remote_db:
                for model_class in SYNC_TABLES:
                    try:
                        await self._sync_table(
                            local_db=local_db,
                            remote_db=remote_db,
                            model_class=model_class,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to sync {model_class.__tablename__}: {e}"
                        )
                await remote_db.commit()

    async def _sync_table(
        self,
        local_db: AsyncSession,
        remote_db: AsyncSession,
        model_class: Type[Base],
    ) -> None:
        """
        Sync a single table from local → remote using UPSERT logic.

        For each local row:
        - If it doesn't exist in remote → INSERT
        - If it exists → UPDATE (merge)
        """
        table_name = model_class.__tablename__
        pk_col_name = list(model_class.__table__.primary_key.columns)[0].name

        # Get all local rows
        local_result = await local_db.execute(select(model_class))
        local_rows = local_result.scalars().all()

        if not local_rows:
            return

        # Get all remote primary keys for comparison
        pk_attr = getattr(model_class, pk_col_name)
        remote_result = await remote_db.execute(select(pk_attr))
        remote_pks = {row[0] for row in remote_result.fetchall()}

        inserted = 0
        updated = 0

        for row in local_rows:
            # Build a dict of column values from the local row
            row_dict = {
                col.name: getattr(row, col.name)
                for col in model_class.__table__.columns
            }
            row_pk = row_dict[pk_col_name]

            if row_pk not in remote_pks:
                # INSERT — row doesn't exist in remote yet
                new_row = model_class(**row_dict)
                remote_db.add(new_row)
                inserted += 1
            else:
                # UPDATE — merge handles the upsert
                await remote_db.merge(model_class(**row_dict))
                updated += 1

        if inserted or updated:
            logger.debug(
                f"  {table_name}: +{inserted} inserted, ~{updated} updated"
            )

    # ── Helpers ──────────────────────────────────────────────────────

    async def _copy_table(
        self,
        source_db: AsyncSession,
        target_db: AsyncSession,
        model_class: Type[Base],
        direction: str = "",
    ) -> int:
        """Copy all rows from source to target for a given model."""
        table_name = model_class.__tablename__

        result = await source_db.execute(select(model_class))
        rows = result.scalars().all()

        count = 0
        for row in rows:
            row_dict = {
                col.name: getattr(row, col.name)
                for col in model_class.__table__.columns
            }
            # Use merge to handle potential PK conflicts gracefully
            target_db.add(model_class(**row_dict))
            count += 1

        if count > 0:
            logger.info(f"  {direction} {table_name}: {count} rows")

        return count

    # ── Manual Sync (for API/admin endpoints) ───────────────────────

    async def force_sync(self) -> dict:
        """Trigger an immediate sync (useful for admin endpoints)."""
        if not self.is_configured:
            return {"status": "error", "message": "Remote DB not configured"}

        try:
            await self._sync_all_tables()
            self._sync_count += 1
            return {"status": "ok", "sync_count": self._sync_count}
        except Exception as e:
            self._last_error = str(e)
            return {"status": "error", "message": str(e)}


# ── Module-level singleton ──────────────────────────────────────────
sync_service = SyncService()
