"""API-key authentication dependency for FastAPI."""

from __future__ import annotations

import hashlib
import secrets
import uuid

import bcrypt
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import get_db
from app.models.db_models import AgentRow, ModelConnectionRow

_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def generate_api_key() -> str:
    """Generate a new Vizhi API key with the configured prefix."""
    token = secrets.token_hex(24)
    return f"{settings.api_key_prefix}{token}"


def hash_api_key(raw_key: str) -> str:
    """Create a bcrypt hash of an API key for safe storage."""
    return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(raw_key: str, hashed: str) -> bool:
    """Verify a raw API key against its bcrypt hash."""
    return bcrypt.checkpw(raw_key.encode(), hashed.encode())


def mask_api_key(raw_key: str) -> str:
    """Return a masked version for display: ``vz_live_a1b2...f3e4``."""
    prefix = settings.api_key_prefix
    body = raw_key.removeprefix(prefix)
    if len(body) <= 8:
        return f"{prefix}{'*' * len(body)}"
    return f"{prefix}{body[:4]}...{body[-4:]}"


def _fast_hash(raw_key: str) -> str:
    """SHA-256 fingerprint for fast DB lookup before bcrypt verify."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


@dataclass(frozen=True)
class ChatCredential:
    """Authenticated credential used by the chat gateway."""

    principal_id: str
    token_type: str
    model_name: str | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class AgentQueueCredential:
    """Authenticated credential used by the on-site agent queue."""

    agent_id: str
    agent_name: str
    user_id: str | None = None


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    raw_key = authorization.removeprefix("Bearer ").strip()
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )
    return raw_key


async def resolve_agent(
    authorization: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> AgentRow:
    """FastAPI dependency – validates the API key and returns the Agent.

    Expects header::

        Authorization: Bearer vz_live_xxxxxxxx
    """
    raw_key = _extract_bearer_token(authorization)

    # Scan agents and bcrypt-verify.  For P0 scale this is fine;
    # P1 adds a SHA-256 fingerprint column for indexed lookup.
    result = await db.execute(select(AgentRow).where(AgentRow.status == "active"))
    agents = result.scalars().all()

    for agent in agents:
        if verify_api_key(raw_key, agent.api_key_hash):
            return agent

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def resolve_chat_credential(
    authorization: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> ChatCredential:
    """Validate a chat token.

    Model tokens are preferred for chat calls because they are already bound to
    a specific provider/model. Agent tokens are accepted as a compatibility path
    and must still provide a model in the request body.
    """
    raw_key = _extract_bearer_token(authorization)

    model_result = await db.execute(
        select(ModelConnectionRow).where(ModelConnectionRow.status == "active")
    )
    for model_connection in model_result.scalars().all():
        if verify_api_key(raw_key, model_connection.api_key_hash):
            return ChatCredential(
                principal_id=model_connection.id,
                token_type="model",
                model_name=model_connection.model_name,
                user_id=model_connection.user_id,
            )

    agent_result = await db.execute(select(AgentRow).where(AgentRow.status == "active"))
    for agent in agent_result.scalars().all():
        if verify_api_key(raw_key, agent.api_key_hash):
            return ChatCredential(
                principal_id=agent.agent_id,
                token_type="agent",
                user_id=agent.user_id,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def resolve_gateway_credential(
    authorization: str | None = Security(_api_key_header),
    x_agent_cid: str | None = Header(default=None, alias="X-Agent-CID"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    db: AsyncSession = Depends(get_db),
) -> ChatCredential:
    """Resolve either a model token or an explicit agent queue credential."""
    if x_agent_cid or x_agent_token:
        if not x_agent_cid or not x_agent_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Both X-Agent-CID and X-Agent-Token are required",
            )
        result = await db.execute(
            select(AgentRow).where(
                AgentRow.agent_id == x_agent_cid,
                AgentRow.status == "active",
            )
        )
        agent = result.scalars().first()
        if not agent or not verify_api_key(x_agent_token, agent.api_key_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid agent credentials",
            )
        return ChatCredential(
            principal_id=agent.agent_id,
            token_type="agent",
            user_id=agent.user_id,
        )

    return await resolve_chat_credential(authorization, db)


async def resolve_agent_queue_credential(
    x_agent_cid: str | None = Header(default=None, alias="X-Agent-CID"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    db: AsyncSession = Depends(get_db),
) -> AgentQueueCredential:
    """Resolve the authenticated agent that is fetching or submitting jobs."""
    return await verify_agent_queue_credentials(
        db,
        agent_cid=x_agent_cid,
        agent_token=x_agent_token,
    )


async def verify_agent_queue_credentials(
    db: AsyncSession,
    *,
    agent_cid: str | None,
    agent_token: str | None,
) -> AgentQueueCredential:
    if not agent_cid or not agent_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Both X-Agent-CID and X-Agent-Token are required",
        )

    result = await db.execute(
        select(AgentRow).where(
            AgentRow.agent_id == agent_cid,
            AgentRow.status == "active",
        )
    )
    agent = result.scalars().first()
    if not agent or not verify_api_key(agent_token, agent.api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )
    return AgentQueueCredential(
        agent_id=agent.agent_id,
        agent_name=agent.name,
        user_id=agent.user_id,
    )


async def optional_agent(
    authorization: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> AgentRow | None:
    """Like ``resolve_agent`` but returns ``None`` instead of raising."""
    if not authorization:
        return None
    try:
        return await resolve_agent(authorization, db)
    except HTTPException:
        return None
