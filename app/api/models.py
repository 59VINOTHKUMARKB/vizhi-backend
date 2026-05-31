"""Model registry / connection API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import generate_api_key, hash_api_key, mask_api_key
from app.db.session import get_db
from app.models.db_models import ModelConnectionRow
from app.schemas.requests import CreateModelConnectionRequest
from app.schemas.responses import ModelConnectionCreatedResponse, ModelConnectionResponse

router = APIRouter(prefix="/v1/models", tags=["models"])
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
    db: AsyncSession = Depends(get_db),
) -> ModelConnectionCreatedResponse:
    raw_key = generate_api_key()

    row = ModelConnectionRow(
        id=f"mt_{uuid.uuid4().hex[:8]}",
        provider=body.provider.lower(),
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
    db: AsyncSession = Depends(get_db),
) -> list[ModelConnectionResponse]:
    """List all registered model connections."""
    result = await db.execute(
        select(ModelConnectionRow).order_by(ModelConnectionRow.created_at.desc())
    )
    return [_row_to_response(row) for row in result.scalars().all()]

@router.get("/registry")
async def model_registry() -> list[dict]:
    """Return the static registry of all known models across providers."""
    return [
        {"model": "gpt-4o", "provider": "openai"},
        {"model": "gpt-4o-mini", "provider": "openai"},
        {"model": "gpt-4.1", "provider": "openai"},
        {"model": "gpt-4.1-mini", "provider": "openai"},
        {"model": "gpt-4.1-nano", "provider": "openai"},
        {"model": "o3", "provider": "openai"},
        {"model": "o3-mini", "provider": "openai"},
        {"model": "o4-mini", "provider": "openai"},
        {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
        {"model": "claude-3-5-sonnet-20241022", "provider": "anthropic"},
        {"model": "claude-3-5-haiku-20241022", "provider": "anthropic"},
        {"model": "claude-3-haiku-20240307", "provider": "anthropic"},
        {"model": "gemini-2.5-flash", "provider": "gemini"},
        {"model": "gemini-2.5-pro", "provider": "gemini"},
        {"model": "gemini-2.0-flash", "provider": "gemini"},
        {"model": "qwen-max", "provider": "qwen"},
        {"model": "qwen-plus", "provider": "qwen"},
        {"model": "qwen-turbo", "provider": "qwen"},
    ]

@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_connection(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ModelConnectionRow).where(ModelConnectionRow.id == model_id))
    if not (row := result.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model connection not found")
    await db.delete(row)
    await db.commit()
