"""Model registry / connection API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import generate_api_key, hash_api_key, mask_api_key
from app.auth.user_auth import get_current_user
from app.db.session import get_db
from app.models.db_models import ModelConnectionRow, UserRow
from app.schemas.requests import CreateModelConnectionRequest
from app.schemas.responses import (
    ModelConnectionCreatedResponse,
    ModelConnectionResponse,
    ModelUsageDetailResponse,
    ModelUsageStats,
    QueryDetailItem,
)

router = APIRouter(prefix="/v1/models", tags=["models"])


_MODEL_CATALOG: list[dict] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "models": [
            {"id": "openai/gpt-4o", "label": "gpt-4o"},
            {"id": "openai/gpt-4o-mini", "label": "gpt-4o-mini"},
            {"id": "openai/gpt-4.1", "label": "gpt-4.1"},
            {"id": "openai/gpt-4.1-mini", "label": "gpt-4.1-mini"},
            {"id": "openai/gpt-4.1-nano", "label": "gpt-4.1-nano"},
            {"id": "openai/o3", "label": "o3"},
            {"id": "openai/o3-mini", "label": "o3-mini"},
            {"id": "openai/o4-mini", "label": "o4-mini"},
        ],
    },
    {
        "id": "claude",
        "label": "Claude",
        "models": [
            {"id": "anthropic/claude-sonnet-4-20250514", "label": "claude-sonnet-4"},
            {"id": "anthropic/claude-3-5-sonnet-20241022", "label": "claude-3.5-sonnet"},
            {"id": "anthropic/claude-3-5-haiku-20241022", "label": "claude-3.5-haiku"},
            {"id": "anthropic/claude-3-haiku-20240307", "label": "claude-3-haiku"},
        ],
    },
    {
        "id": "llama",
        "label": "Llama",
        "models": [
            {
                "id": "llama/meta-llama/Llama-3.1-8B-Instruct",
                "label": "Llama 3.1 8B Instruct",
            },
            {
                "id": "llama/meta-llama/Llama-3.2-3B-Instruct",
                "label": "Llama 3.2 3B Instruct",
            },
        ],
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "models": [
            {
                "id": "mistral/mistralai/Mistral-7B-Instruct-v0.3",
                "label": "Mistral 7B Instruct",
            },
            {
                "id": "mistral/mistralai/Mixtral-8x7B-Instruct-v0.1",
                "label": "Mixtral 8x7B Instruct",
            },
        ],
    },
    {
        "id": "deepseek",   
        "label": "DeepSeek",
        "models": [
            {
                "id": "deepseek/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "label": "DeepSeek R1 Distill Qwen 7B",
            },
        ],
    },
]


def _catalog_model_ids(provider_id: str) -> set[str]:
    for provider in _MODEL_CATALOG:
        if provider["id"] == provider_id:
            return {model["id"] for model in provider["models"]}
    return set()


def _row_to_response(row: ModelConnectionRow) -> ModelConnectionResponse:
    return ModelConnectionResponse(
        id=row.id,
        provider=row.provider,
        model_name=row.model_name,
        status=row.status,
        metadata=row.metadata_,
        usage_count=row.usage_count,
        masked_key=row.masked_key,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_model_connection(
    body: CreateModelConnectionRequest,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModelConnectionCreatedResponse:
    provider_id = body.provider.lower()
    if body.model_name not in _catalog_model_ids(provider_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model is not available for the selected provider",
        )

    raw_key = generate_api_key()

    row = ModelConnectionRow(
        id=f"mt_{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        provider=provider_id,
        model_name=body.model_name,
        api_key_hash=hash_api_key(raw_key),
        masked_key=mask_api_key(raw_key),
        status="active",
        metadata_=body.metadata,
    )
    db.add(row)
    await db.flush()
    await db.commit()

    return ModelConnectionCreatedResponse(
        model_connection=_row_to_response(row),
        api_key=raw_key,
    )


@router.get("")
async def list_models(
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelConnectionResponse]:
    """List all registered model connections."""
    result = await db.execute(
        select(ModelConnectionRow)
        .where(ModelConnectionRow.user_id == user.id)
        .order_by(ModelConnectionRow.created_at.desc())
    )
    return [_row_to_response(row) for row in result.scalars().all()]

@router.get("/registry")
async def model_registry() -> list[dict]:
    """Return provider/model options for client dropdowns."""
    return _MODEL_CATALOG

@router.get("/{model_id}/usage")
async def get_model_usage(
    model_id: str,
    limit: int = 50,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModelUsageDetailResponse:
    """Get detailed usage statistics and query history for a model connection."""
    from sqlalchemy import func
    import json
    from app.models.db_models import QueryRow, ResponseRow
    
    # Get the model connection
    result = await db.execute(
        select(ModelConnectionRow).where(
            ModelConnectionRow.id == model_id,
            ModelConnectionRow.user_id == user.id,
        )
    )
    model_row = result.scalar_one_or_none()
    if not model_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model connection not found")
    
    # Get aggregate statistics
    from sqlalchemy import case as sql_case, or_
    
    # Handle both "gpt-4o" and "openai/gpt-4o" formats
    model_name_short = model_row.model_name.split('/')[-1]  # Extract "gpt-4o" from "openai/gpt-4o"
    
    stats_result = await db.execute(
        select(
            func.count(QueryRow.id),
            func.coalesce(func.sum(ResponseRow.input_tokens), 0),
            func.coalesce(func.sum(ResponseRow.output_tokens), 0),
            func.coalesce(func.sum(ResponseRow.estimated_cost), 0.0),
            func.coalesce(func.avg(ResponseRow.latency_ms), 0),
            func.sum(sql_case((ResponseRow.status_code >= 400, 1), else_=0)),
        )
        .select_from(QueryRow)
        .join(ResponseRow, ResponseRow.query_id == QueryRow.id)
        .where(
            or_(
                QueryRow.model == model_row.model_name,  # Match full name "openai/gpt-4o"
                QueryRow.model == model_name_short,      # Match short name "gpt-4o"
            ),
            QueryRow.user_id == user.id,
        )
    )
    stats_row = stats_result.one()
    
    total_requests = stats_row[0] or 0
    total_input = stats_row[1] or 0
    total_output = stats_row[2] or 0
    total_cost = float(stats_row[3] or 0.0)
    avg_latency = int(stats_row[4] or 0)
    error_count = stats_row[5] or 0
    success_rate = ((total_requests - error_count) / total_requests * 100) if total_requests > 0 else 100.0
    
    stats = ModelUsageStats(
        total_requests=total_requests,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
        total_cost=total_cost,
        avg_latency_ms=avg_latency,
        error_count=error_count,
        success_rate=round(success_rate, 2),
    )
    
    # Get recent queries with responses
    queries_result = await db.execute(
        select(QueryRow)
        .where(
            or_(
                QueryRow.model == model_row.model_name,  # Match full name
                QueryRow.model == model_name_short,      # Match short name
            ),
            QueryRow.user_id == user.id,
        )
        .order_by(QueryRow.timestamp.desc())
        .limit(limit)
    )
    queries = queries_result.scalars().all()
    
    query_details: list[QueryDetailItem] = []
    for q in queries:
        # Get response for this query
        resp_result = await db.execute(
            select(ResponseRow).where(ResponseRow.query_id == q.id)
        )
        r = resp_result.scalar_one_or_none()
        
        # Parse input messages
        try:
            prompt = json.loads(q.input_messages) if q.input_messages else []
        except json.JSONDecodeError:
            prompt = []
        
        # Extract response text
        response_text = ""
        if r and r.response:
            try:
                response_data = json.loads(r.response)
                # Try to extract content from different response formats
                if isinstance(response_data, dict):
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        choice = response_data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            response_text = choice["message"]["content"]
                        elif "text" in choice:
                            response_text = choice["text"]
                    elif "content" in response_data:
                        response_text = response_data["content"]
            except json.JSONDecodeError:
                response_text = r.response[:500] if r.response else ""
        
        query_details.append(
            QueryDetailItem(
                query_id=q.id,
                timestamp=q.timestamp.isoformat() if q.timestamp else "",
                agent_id=q.agent_id,
                prompt=prompt,
                response_text=response_text,
                input_tokens=r.input_tokens if r else 0,
                output_tokens=r.output_tokens if r else 0,
                latency_ms=r.latency_ms if r else 0,
                status_code=r.status_code if r else 0,
                estimated_cost=r.estimated_cost if r else 0.0,
                error_message=r.error_message if r else None,
            )
        )
    
    return ModelUsageDetailResponse(
        model_connection=_row_to_response(model_row),
        stats=stats,
        recent_queries=query_details,
    )


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_connection(
    model_id: str,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ModelConnectionRow).where(
            ModelConnectionRow.id == model_id,
            ModelConnectionRow.user_id == user.id,
        )
    )
    if not (row := result.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model connection not found")
    await db.delete(row)
    await db.commit()
