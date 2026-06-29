"""SQLAlchemy ORM models for the Vizhi backend."""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ── Agents ──────────────────────────────────────────────────────────────


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email_verified: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AuthAccountRow(Base):
    __tablename__ = "auth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_auth_provider_user"),
        UniqueConstraint("user_id", "provider", name="uq_auth_user_provider"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    masked_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full token (encrypted)
    tags: Mapped[str] = mapped_column(Text, default="[]")   
    status: Mapped[str] = mapped_column(Text, default="active")
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AgentRuntimeRow(Base):
    __tablename__ = "agent_runtime"

    agent_id: Mapped[str] = mapped_column(Text, primary_key=True)
    device_name: Mapped[str] = mapped_column(Text, default="")
    os_name: Mapped[str] = mapped_column(Text, default="")
    agent_version: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="offline")
    last_heartbeat: Mapped[_dt.datetime | None] = mapped_column(DateTime, nullable=True)
    available_engines: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ── Model Connections ───────────────────────────────────────────────────


class ModelConnectionRow(Base):
    __tablename__ = "model_connections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    masked_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full token (encrypted)
    status: Mapped[str] = mapped_column(Text, default="active")
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


# ── Queries ─────────────────────────────────────────────────────────────


class QueryRow(Base):
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    sdk_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_messages: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    endpoint: Mapped[str] = mapped_column(Text, default="/v1/chat/completions")
    timestamp: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


# ── Responses ───────────────────────────────────────────────────────────


class ResponseRow(Base):
    __tablename__ = "responses"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    query_id: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class AgentJobRow(Base):
    __tablename__ = "agent_jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    query_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    sdk_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str] = mapped_column(Text, default="/v1/chat/completions")
    kind: Mapped[str] = mapped_column(Text, default="chat")
    input_payload: Mapped[str] = mapped_column(Text, nullable=False)
    stream: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[str] = mapped_column("metadata", Text, default="{}")
    status: Mapped[str] = mapped_column(Text, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    claimed_at: Mapped[_dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[_dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
