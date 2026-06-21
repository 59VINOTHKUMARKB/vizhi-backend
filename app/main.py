"""Main FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.db.init_db import init_db
from app.db.sync_service import sync_service
from app.api.agents import router as agents_router
from app.api.agent_queue import router as agent_queue_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.models import router as models_router
from app.api.queries import router as queries_router
from app.api.metrics import router as metrics_router
from app.api.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle — init DB, hydrate from remote, start background sync."""

    # 1. Create tables on both local SQLite and remote Supabase PostgreSQL
    await init_db()

    # 2. If local DB is empty (fresh Docker container), hydrate from remote
    await sync_service.hydrate_local_from_remote()

    # 3. Start background sync loop (local → remote, every N seconds)
    await sync_service.start()

    yield

    # 4. On shutdown: final flush of pending data to remote
    await sync_service.stop()


app = FastAPI(
    title="Vizhi API Gateway",
    description="Unified API Gateway and Query Tracking Core for AI Agents",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware for Frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(agent_queue_router)
app.include_router(chat_router)
app.include_router(models_router)
app.include_router(queries_router)
app.include_router(metrics_router)
app.include_router(dashboard_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Health check/root endpoint."""
    return {
        "name": "Vizhi API Gateway",
        "status": "healthy",
        "version": "1.0.0",
    }
