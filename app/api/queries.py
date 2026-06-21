"""Query history retrieval endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.user_auth import get_current_user
from app.db.session import get_db
from app.models.db_models import QueryRow, ResponseRow, UserRow
from app.schemas.responses import RequestEventResponse

router = APIRouter(prefix="/v1/queries", tags=["queries"])


@router.get("")
async def list_queries(
    agent_id: str | None = None,
    model: str | None = None,
    limit: int = 50,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RequestEventResponse]:
    """List queries with optional filters."""
    stmt = (
        select(QueryRow)
        .where(QueryRow.user_id == user.id)
        .order_by(desc(QueryRow.timestamp))
        .limit(limit)
    )
    if agent_id:
        stmt = stmt.where(QueryRow.agent_id == agent_id)
    if model:
        stmt = stmt.where(QueryRow.model == model)

    result = await db.execute(stmt)
    queries = result.scalars().all()

    items: list[RequestEventResponse] = []
    for q in queries:
        r_result = await db.execute(
            select(ResponseRow).where(ResponseRow.query_id == q.id)
        )
        r = r_result.scalars().first()
        items.append(
            RequestEventResponse(
                id=q.id,
                timestamp=q.timestamp.isoformat() if q.timestamp else "",
                agent_id=q.agent_id,
                model=q.model,
                provider=q.provider,
                endpoint=q.endpoint,
                status=r.status_code if r else 0,
                latency_ms=r.latency_ms if r else 0,
                input_tokens=r.input_tokens if r else 0,
                output_tokens=r.output_tokens if r else 0,
                estimated_cost=r.estimated_cost if r else 0.0,
                error_message=r.error_message if r else None,
            )
        )
    return items


@router.get("/{query_id}")
async def get_query(
    query_id: str,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestEventResponse:
    """Get a single query + response by ID."""
    result = await db.execute(
        select(QueryRow).where(QueryRow.id == query_id, QueryRow.user_id == user.id)
    )
    q = result.scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Query not found")

    r_result = await db.execute(
        select(ResponseRow).where(ResponseRow.query_id == q.id)
    )
    r = r_result.scalars().first()

    return RequestEventResponse(
        id=q.id,
        timestamp=q.timestamp.isoformat() if q.timestamp else "",
        agent_id=q.agent_id,
        model=q.model,
        provider=q.provider,
        endpoint=q.endpoint,
        status=r.status_code if r else 0,
        latency_ms=r.latency_ms if r else 0,
        input_tokens=r.input_tokens if r else 0,
        output_tokens=r.output_tokens if r else 0,
        estimated_cost=r.estimated_cost if r else 0.0,
        error_message=r.error_message if r else None,
    )
