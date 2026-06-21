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
from app.schemas.responses import ModelConnectionCreatedResponse, ModelConnectionResponse

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
