"""Database initialization — creates tables on both local and remote databases."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.config.settings import settings
from app.db.session import local_engine, remote_engine
from app.models.db_models import Base

logger = logging.getLogger("vizhi.db")


async def _sync_sqlite_agents_schema(conn) -> None:
    """Remove stale dev columns left behind by create_all-only schema changes."""
    result = await conn.execute(text("PRAGMA table_info(agents)"))
    columns = {row[1] for row in result.fetchall()}
    stale_columns = {"owner", "preferred_model"} & columns
    if not stale_columns:
        return

    await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    await conn.exec_driver_sql(
        """
        CREATE TABLE agents_new (
            id TEXT NOT NULL,
            user_id TEXT,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            api_key_hash TEXT NOT NULL,
            masked_key TEXT NOT NULL,
            tags TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (agent_id)
        )
        """
    )
    await conn.exec_driver_sql(
        """
        INSERT INTO agents_new (
            id,
            user_id,
            agent_id,
            name,
            description,
            api_key_hash,
            masked_key,
            tags,
            status,
            created_at,
            updated_at
        )
        SELECT
            id,
            user_id,
            agent_id,
            name,
            description,
            api_key_hash,
            masked_key,
            tags,
            status,
            created_at,
            updated_at
        FROM agents
        """
    )
    await conn.exec_driver_sql("DROP TABLE agents")
    await conn.exec_driver_sql("ALTER TABLE agents_new RENAME TO agents")
    await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


async def _ensure_sqlite_column(
    conn,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    columns = {row[1] for row in result.fetchall()}
    if column_name in columns:
        return
    await conn.exec_driver_sql(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )


async def init_db() -> None:
    """Create tables on both local and remote databases."""

    # ── 1. Initialize LOCAL database (SQLite) ───────────────────────
    logger.info("Initializing local database...")
    async with local_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await _ensure_sqlite_column(
                conn,
                table_name="agents",
                column_name="user_id",
                column_definition="TEXT",
            )
            await _ensure_sqlite_column(
                conn,
                table_name="model_connections",
                column_name="user_id",
                column_definition="TEXT",
            )
            await _ensure_sqlite_column(
                conn,
                table_name="queries",
                column_name="user_id",
                column_definition="TEXT",
            )
            await _ensure_sqlite_column(
                conn,
                table_name="agents",
                column_name="token_name",
                column_definition="TEXT",
            )
            await _ensure_sqlite_column(
                conn,
                table_name="agents",
                column_name="last_used_at",
                column_definition="DATETIME",
            )
            await _sync_sqlite_agents_schema(conn)
    logger.info("✅ Local database ready")

    # ── 2. Initialize REMOTE database (Supabase PostgreSQL) ─────────
    if remote_engine is not None:
        try:
            logger.info("Initializing remote database (Supabase)...")
            async with remote_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Remote database ready")
        except Exception as e:
            logger.error(
                f"⚠️  Remote database init failed: {e} — "
                "continuing with local-only mode"
            )
    else:
        logger.info("No remote database configured — local-only mode")
