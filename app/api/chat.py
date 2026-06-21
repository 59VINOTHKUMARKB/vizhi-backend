
"""Core chat completion gateway endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import ChatCredential, resolve_gateway_credential
from app.db.session import async_session_factory, get_db
from app.models.db_models import AgentJobRow, QueryRow, ResponseRow
from app.schemas.requests import ChatCompletionRequest
from app.schemas.responses import (
    ChatChoice,
    ChatChoiceMessage,
    ChatCompletionResponse,
    ChatUsage,
    VizhiMetadata,
)
from app.services.agent_ws import agent_ws_manager
from app.services.persistence import (
    persist_agent_job,
    persist_query,
    persist_response,
)
from app.services.router import provider_router

router = APIRouter(prefix="/v1", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    credential: ChatCredential = Depends(resolve_gateway_credential),
    db: AsyncSession = Depends(get_db),
) -> ChatCompletionResponse:
    
    """OpenRouter-style chat completion gateway.

    Model tokens continue to resolve providers directly.
    Agent tokens are queued and fulfilled by the on-site agent.
    """
    requested_model = body.model
    token_model = credential.model_name
    if token_model and requested_model and requested_model != token_model:
        raise HTTPException(
            status_code=400,
            detail="Requested model does not match the model bound to this token",
        )

    model_name = token_model or requested_model
    if not model_name:
        raise HTTPException(
            status_code=400,
            detail="Model is required when using an agent token",
        )

    if credential.token_type == "agent":
        provider_name = "agent"
        resolved_model = model_name
        provider = None
    else:
        try:
            provider, resolved_model = provider_router.resolve(model_name, body.call_sdk)
            provider_name = provider.provider_name
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    messages_raw = [m.model_dump() for m in body.messages]
    if credential.token_type == "agent":
        try:
            query_row = await persist_query(
                db,
                agent_id=credential.principal_id,
                user_id=credential.user_id,
                provider=provider_name,
                model=resolved_model,
                sdk_type=body.call_sdk,
                messages=messages_raw,
            )

            job_row = await persist_agent_job(
                db,
                query_id=query_row.id,
                user_id=credential.user_id,
                agent_id=credential.principal_id,
                provider=provider_name,
                model=resolved_model,
                sdk_type=body.call_sdk,
                messages=messages_raw,
                endpoint="/v1/chat/completions",
                kind="chat",
                stream=False,
                metadata={"source": "chat-gateway"},
            )
            await db.commit()
            try:
                await agent_ws_manager.notify(
                    credential.principal_id,
                    {
                        "type": "job_available",
                        "agent_id": credential.principal_id,
                        "job_id": job_row.id,
                    },
                )
            except Exception:
                pass
            return await _wait_for_agent_result(
                query_row=query_row,
                job_id=job_row.id,
                agent_id=credential.principal_id,
                timeout_seconds=120,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Agent queue request failed")
            raise HTTPException(
                status_code=500,
                detail=f"Agent queue request failed: {exc}",
            ) from exc

    start = time.perf_counter_ns()
    try:
        assert provider is not None
        result = await provider.chat_completion(
            model=resolved_model,
            messages=messages_raw,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except Exception as exc:
        latency = (time.perf_counter_ns() - start) // 1_000_000
        await persist_response(
            db,
            query_id=query_row.id,
            status_code=502,
            error_message=str(exc),
            latency_ms=latency,
        )
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"Provider error: {exc}",
        )

    await persist_response(
        db,
        query_id=query_row.id,
        provider_response=result,
        status_code=200,
    )

    return ChatCompletionResponse(
        id=f"vzr_{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=result.model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(content=result.content),
                finish_reason=result.finish_reason,
            )
        ],
        usage=ChatUsage(
            prompt_tokens=result.input_tokens,
            completion_tokens=result.output_tokens,
            total_tokens=result.input_tokens + result.output_tokens,
        ),
        vizhi_metadata=VizhiMetadata(
            agent_id=credential.principal_id,
            provider=result.provider,
            latency_ms=result.latency_ms,
            query_id=query_row.id,
        ),
    )


async def _wait_for_agent_result(
    *,
    query_row: QueryRow,
    job_id: str,
    agent_id: str,
    timeout_seconds: int = 120,
) -> ChatCompletionResponse:
    deadline = time.perf_counter() + timeout_seconds
    last_job_row: AgentJobRow | None = None
    while time.perf_counter() < deadline:
        async with async_session_factory() as poll_db:
            response_result = await poll_db.execute(
                select(ResponseRow).where(ResponseRow.query_id == query_row.id)
            )
            response_row = response_result.scalars().first()
            job_result = await poll_db.execute(
                select(AgentJobRow).where(AgentJobRow.id == job_id)
            )
            job_row = job_result.scalars().first()
            if job_row is not None:
                last_job_row = job_row
            if response_row and job_row:
                if response_row.status_code >= 400 or job_row.status in {"failed", "cancelled"}:
                    raise HTTPException(
                        status_code=502,
                        detail=response_row.error_message
                        or job_row.error_message
                        or "Agent job failed",
                    )
                payload = {}
                if response_row.response:
                    try:
                        payload = json.loads(response_row.response)
                    except Exception:
                        payload = {"content": response_row.response}
                return _build_chat_response(
                    query_row=query_row,
                    response_row=response_row,
                    payload=payload,
                    agent_id=agent_id,
                )
            if job_row and job_row.status in {"failed", "cancelled"}:
                raise HTTPException(
                    status_code=502,
                    detail=job_row.error_message or "Agent job failed",
                )
        await asyncio.sleep(1.0)

    raise HTTPException(
        status_code=504,
        detail={
            "message": "Agent job is still queued",
            "query_id": query_row.id,
            "job_id": job_id,
            "agent_id": agent_id,
            "last_status": last_job_row.status if last_job_row else "missing",
        },
    )


def _build_chat_response(
    *,
    query_row: QueryRow,
    response_row: ResponseRow,
    payload: dict,
    agent_id: str,
) -> ChatCompletionResponse:
    content = _extract_content(payload)
    prompt_tokens = _extract_usage(payload, "prompt_tokens", response_row.input_tokens)
    completion_tokens = _extract_usage(
        payload, "completion_tokens", response_row.output_tokens
    )
    return ChatCompletionResponse(
        id=f"vzr_{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=str(payload.get("model") or query_row.model),
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(content=content),
                finish_reason=str(payload.get("finish_reason", "stop")),
            )
        ],
        usage=ChatUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        vizhi_metadata=VizhiMetadata(
            agent_id=agent_id,
            provider=str(payload.get("provider") or query_row.provider),
            latency_ms=response_row.latency_ms,
            query_id=query_row.id,
        ),
    )


def _extract_content(payload: dict) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message") or {}
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content", ""))
            if first.get("text") is not None:
                return str(first.get("text", ""))
    if isinstance(payload.get("message"), dict):
        return str(payload["message"].get("content", ""))
    if payload.get("response") is not None:
        return str(payload.get("response", ""))
    if payload.get("content") is not None:
        return str(payload.get("content", ""))
    return ""


def _extract_usage(payload: dict, key: str, fallback: int) -> int:
    usage = payload.get("usage")
    if isinstance(usage, dict) and usage.get(key) is not None:
        try:
            return int(usage.get(key, fallback))
        except Exception:
            pass
    if key == "prompt_tokens" and payload.get("prompt_eval_count") is not None:
        return int(payload.get("prompt_eval_count", fallback))
    if key == "completion_tokens" and payload.get("eval_count") is not None:
        return int(payload.get("eval_count", fallback))
    return int(fallback or 0)
