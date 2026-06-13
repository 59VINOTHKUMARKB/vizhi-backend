"""Main FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.db.init_db import init_db
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
    """Lifecycle events manager — initializes the database on startup."""
    # Create database tables if they do not exist
    await init_db()
    yield


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
