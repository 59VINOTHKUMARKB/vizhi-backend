"""SQLAlchemy ORM models for the Vizhi backend."""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ── Agents ──────────────────────────────────────────────────────────────


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    masked_key: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")   
    status: Mapped[str] = mapped_column(Text, default="active")
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
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    masked_key: Mapped[str] = mapped_column(Text, nullable=False)
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
