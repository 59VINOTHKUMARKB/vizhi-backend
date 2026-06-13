"""Pydantic response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Chat Completion Response (OpenAI-compatible) ────────────────────────


class UserResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    name: str = ""
    avatar_url: str = ""


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChatChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatChoiceMessage
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class VizhiMetadata(BaseModel):
    agent_id: str
    provider: str
    latency_ms: int
    query_id: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage
    vizhi_metadata: VizhiMetadata


# ── Agent Response ──────────────────────────────────────────────────────


class AgentResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    description: str
    tags: list[str]
    status: str
    masked_key: str
    created_at: str
    updated_at: str


class AgentCreatedResponse(BaseModel):
    """Returned only on creation — includes the raw API key once."""
    agent: AgentResponse
    api_key: str = Field(
        ..., description="Full API key – shown only once, store securely"
    )


class AgentRuntimeResponse(BaseModel):
    agent_id: str
    device_name: str = ""
    os_name: str = ""
    agent_version: str = ""
    status: str = "offline"
    last_heartbeat: str | None = None
    available_engines: list[str] = Field(default_factory=list)
    updated_at: str = ""


class AgentJobQueueItemResponse(BaseModel):
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


class AgentJobCompletionResponse(BaseModel):
    ok: bool = True
    job_id: str
    status: str
    query_id: str
    completed_at: str = ""


# ── Model Connection Response ───────────────────────────────────────────


class ModelConnectionResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    status: str
    metadata: str | None = None
    usage_count: int = 0
    masked_key: str
    created_at: str


class ModelConnectionCreatedResponse(BaseModel):
    model_connection: ModelConnectionResponse
    api_key: str = Field(
        ..., description="Full Vizhi model token returned once on creation"
    )


# ── Query / Response history ────────────────────────────────────────────


class QueryHistoryItem(BaseModel):
    id: str
    agent_id: str
    provider: str
    model: str
    sdk_type: str | None = None
    endpoint: str
    timestamp: str


class RequestEventResponse(BaseModel):
    """Combined query + response for dashboard / monitoring."""
    id: str
    timestamp: str
    agent_id: str
    model: str
    provider: str
    endpoint: str
    status: int
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    error_message: str | None = None


# ── Metrics ─────────────────────────────────────────────────────────────


class MetricPoint(BaseModel):
    time: str
    requests: int
    input_tokens: int
    output_tokens: int
    latency: int
    errors: int


class MetricsResponse(BaseModel):
    metric_series: list[MetricPoint]
    requests: list[RequestEventResponse]


# ── Dashboard ───────────────────────────────────────────────────────────


class DashboardTotals(BaseModel):
    agents: int
    model_tokens: int
    requests_today: int
    tokens_consumed: int
    errors: int
    active_models: int


class DashboardResponse(BaseModel):
    totals: DashboardTotals
    metric_series: list[MetricPoint]
    recent_requests: list[RequestEventResponse]
