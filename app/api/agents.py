"""Agent CRUD API endpoints."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import generate_api_key, hash_api_key, mask_api_key
from app.auth.user_auth import get_current_user
from app.db.session import get_db
from app.models.db_models import AgentRow, UserRow
from app.schemas.requests import CreateAgentRequest, UpdateAgentRequest
from app.schemas.responses import AgentCreatedResponse, AgentResponse

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _agent_to_response(row: AgentRow) -> AgentResponse:
    tags = json.loads(row.tags) if row.tags else []
    return AgentResponse(
        id=row.id,
        agent_id=row.agent_id,
        name=row.name,
        description=row.description or "",
        tags=tags if isinstance(tags, list) else [],
        status=row.status,
        masked_key=row.masked_key,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


async def _generate_agent_cid(db: AsyncSession) -> str:
    while True:
        cid = f"ag_{uuid.uuid4().hex[:10]}"
        existing = await db.execute(select(AgentRow.id).where(AgentRow.agent_id == cid))
        if existing.scalar_one_or_none() is None:
            return cid


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentRequest,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentCreatedResponse:
    """Create a new agent and generate an API key."""
    cid = await _generate_agent_cid(db)
    raw_key = generate_api_key()
    tags = [t.strip() for t in body.tags.split(",") if t.strip()] if body.tags else []

    row = AgentRow(
        id=uuid.uuid4().hex[:12],
        user_id=user.id,
        agent_id=cid,
        name=body.name,
        description=body.description,
        api_key_hash=hash_api_key(raw_key),
        masked_key=mask_api_key(raw_key),
        tags=json.dumps(tags),
        status="active",
    )
    db.add(row)
    await db.flush()

    return AgentCreatedResponse(
        agent=_agent_to_response(row),
        api_key=raw_key,
    )


@router.get("")
async def list_agents(
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    """List all agents."""
    result = await db.execute(
        select(AgentRow)
        .where(AgentRow.user_id == user.id)
        .order_by(AgentRow.created_at.desc())
    )
    return [_agent_to_response(row) for row in result.scalars().all()]


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Get a single agent by agent_id (CID)."""
    result = await db.execute(
        select(AgentRow).where(AgentRow.agent_id == agent_id, AgentRow.user_id == user.id)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(row)


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Update agent fields."""
    result = await db.execute(
        select(AgentRow).where(AgentRow.agent_id == agent_id, AgentRow.user_id == user.id)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.tags is not None:
        row.tags = json.dumps([t.strip() for t in body.tags.split(",") if t.strip()])
    if body.status is not None:
        row.status = body.status

    await db.flush()
    return _agent_to_response(row)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an agent by its CID."""
    result = await db.execute(
        select(AgentRow).where(AgentRow.agent_id == agent_id, AgentRow.user_id == user.id)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(row)
