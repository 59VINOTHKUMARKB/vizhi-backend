"""Metrics retrieval endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.user_auth import get_current_user
from app.db.session import get_db
from app.models.db_models import UserRow
from app.schemas.responses import MetricsResponse
from app.services.persistence import build_metrics

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


@router.get("")
async def get_metrics(
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MetricsResponse:
    """Return aggregated metrics: timeseries + recent requests."""
    return await build_metrics(db, user_id=user.id)
