"""Pydantic request schemas for API validation."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Chat Completion ─────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str = Field(..., examples=["user", "assistant", "system"])
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = Field(
        None,
        examples=["openai/gpt-4o-mini", "anthropic/claude-sonnet-4-20250514"],
        description=(
            "Optional for model-token calls. Agent-token calls must provide it."
        ),
    )
    messages: list[ChatMessage]
    call_sdk: str | None = Field(
        None,
        description="SDK adapter hint: openai-sdk, claude-sdk, raw-http",
        examples=["openai-sdk"],
    )
    temperature: float = Field(1.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=128_000)


# ── Frontend Authentication ─────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field("", max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., min_length=20)


# ── Agent CRUD ──────────────────────────────────────────────────────────


class CreateAgentRequest(BaseModel):
    name: str = Field(..., min_length=2)
    description: str = Field("", min_length=0)
    tags: str = Field("", description="Comma-separated tags")
    token_name: str | None = Field(None, max_length=120, description="Optional friendly label for this token")


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: str | None = None
    status: str | None = None


# ── Model Connection ───────────────────────────────────────────────────


class CreateModelConnectionRequest(BaseModel):
    provider: str = Field(..., examples=["openai", "anthropic", "gemini", "qwen", "ollama"])
    model_name: str = Field(..., examples=["gpt-4o-mini"])
    metadata: str | None = None


# ── On-site agent queue ────────────────────────────────────────────────


class AgentRegisterRequest(BaseModel):
    agent_id: str = Field(..., min_length=2)
    device_name: str = Field("", max_length=120)
    os_name: str = Field("", max_length=120)
    agent_version: str = Field("", max_length=64)
    available_engines: list[str] = Field(default_factory=list)


class AgentHeartbeatRequest(BaseModel):
    agent_id: str = Field(..., min_length=2)
    device_name: str = Field("", max_length=120)
    os_name: str = Field("", max_length=120)
    agent_version: str = Field("", max_length=64)
    available_engines: list[str] = Field(default_factory=list)
    status: str = Field("online", max_length=32)
    active_job_id: str = Field("", max_length=64)
    active_engine: str = Field("", max_length=120)
    queue_depth: int = 0


class AgentJobQueueItem(BaseModel):
    id: str
    query_id: str
    agent_id: str = ""
    provider: str
    model: str
    sdk_type: str | None = None
    endpoint: str
    kind: str = "chat"
    engine: str = ""
    input: dict = Field(default_factory=dict)
    stream: bool = False
    metadata: dict = Field(default_factory=dict)
    attempt_count: int = 0


class AgentJobCompletionRequest(BaseModel):
    job_id: str = Field(..., min_length=2)
    status: str = Field("completed", max_length=32)
    output: dict = Field(default_factory=dict)
    error: str = ""
    usage: dict = Field(default_factory=dict)
    completed_at: str = ""
