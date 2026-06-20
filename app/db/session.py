"""Async SQLAlchemy session factory — supports local + remote engines."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings

# ── Local Engine (SQLite) — used for all API read/write ─────────────
local_engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite requires `check_same_thread=False` for async usage.
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)

local_session_factory = async_sessionmaker(
    local_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Remote Engine (Supabase PostgreSQL) — used only by SyncService ──
remote_engine = None
remote_session_factory = None

if settings.remote_database_url:
    remote_engine = create_async_engine(
        settings.remote_database_url,
        echo=False,
        pool_size=5,          # Keep connection pool small (free tier friendly)
        max_overflow=2,
        pool_recycle=300,     # Recycle connections every 5 min
    )
    remote_session_factory = async_sessionmaker(
        remote_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

# ── Backward-compatible aliases ─────────────────────────────────────
# Existing code uses `engine` and `async_session_factory` — these now
# point to the LOCAL database so nothing else needs to change.
engine = local_engine
async_session_factory = local_session_factory


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields a LOCAL db session."""
    async with local_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_remote_db() -> AsyncSession | None:  # type: ignore[misc]
    """FastAPI dependency that yields a REMOTE db session, or None."""
    if remote_session_factory is None:
        yield None
        return

    async with remote_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
