"""On-site agent registration and job queue endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import resolve_agent_queue_credential, verify_agent_queue_credentials
from app.db.session import async_session_factory, get_db
from app.schemas.requests import (
    AgentHeartbeatRequest,
    AgentJobCompletionRequest,
    AgentRegisterRequest,
)
from app.schemas.responses import (
    AgentJobQueueItemResponse,
    AgentJobCompletionResponse,
    AgentRuntimeResponse,
)
from app.services.persistence import (
    claim_next_agent_job,
    complete_agent_job,
    upsert_agent_runtime,
)
from app.services.agent_ws import agent_ws_manager

router = APIRouter(tags=["agent-queue"])


@router.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket) -> None:
    agent_cid = websocket.headers.get("x-agent-cid")
    agent_token = websocket.headers.get("x-agent-token")
    async with async_session_factory() as db:
        credential = await verify_agent_queue_credentials(
            db,
            agent_cid=agent_cid,
            agent_token=agent_token,
        )
    await websocket.accept()
    await agent_ws_manager.connect(credential.agent_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "agent_id": credential.agent_id})
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except Exception:
                payload = {"type": "message", "raw": message}
            if str(payload.get("type", "")).lower() in {"ping", "heartbeat"}:
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await agent_ws_manager.disconnect(credential.agent_id)


@router.post("/agents/register")
async def register_agent(
    body: AgentRegisterRequest,
    credential=Depends(resolve_agent_queue_credential),
    db: AsyncSession = Depends(get_db),
) -> AgentRuntimeResponse:
    if body.agent_id and body.agent_id != credential.agent_id:
        raise HTTPException(status_code=400, detail="Agent CID does not match the authenticated agent")
    row = await upsert_agent_runtime(
        db,
        agent_id=credential.agent_id,
        device_name=body.device_name,
        os_name=body.os_name,
        agent_version=body.agent_version,
        status="online",
        available_engines=body.available_engines,
    )
    await db.refresh(row)
    return _runtime_to_response(row)


@router.post("/agents/heartbeat")
async def agent_heartbeat(
    body: AgentHeartbeatRequest,
    credential=Depends(resolve_agent_queue_credential),
    db: AsyncSession = Depends(get_db),
) -> AgentRuntimeResponse:
    if body.agent_id and body.agent_id != credential.agent_id:
        raise HTTPException(status_code=400, detail="Agent CID does not match the authenticated agent")
    row = await upsert_agent_runtime(
        db,
        agent_id=credential.agent_id,
        device_name=body.device_name,
        os_name=body.os_name,
        agent_version=body.agent_version,
        status=body.status,
        available_engines=body.available_engines,
    )
    await db.refresh(row)
    return _runtime_to_response(row)


@router.get("/jobs/next")
async def next_job(
    credential=Depends(resolve_agent_queue_credential),
    db: AsyncSession = Depends(get_db),
) -> AgentJobQueueItemResponse:
    job = await claim_next_agent_job(db, agent_id=credential.agent_id)
    if not job:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _job_to_response(job)


@router.post("/jobs/submit")
async def submit_job_completion(
    body: AgentJobCompletionRequest,
    credential=Depends(resolve_agent_queue_credential),
    db: AsyncSession = Depends(get_db),
) -> AgentJobCompletionResponse:
    try:
        job, _response = await complete_agent_job(
            db,
            agent_id=credential.agent_id,
            job_id=body.job_id,
            status=body.status,
            output=body.output,
            error=body.error,
            usage=body.usage,
            completed_at=body.completed_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentJobCompletionResponse(
        job_id=job.id,
        status=job.status,
        query_id=job.query_id,
        completed_at=job.completed_at.isoformat() if job.completed_at else "",
    )


def _runtime_to_response(row) -> AgentRuntimeResponse:
    engines = []
    if row.available_engines:
        try:
            engines = json.loads(row.available_engines)
        except Exception:
            engines = []
    return AgentRuntimeResponse(
        agent_id=row.agent_id,
        device_name=row.device_name or "",
        os_name=row.os_name or "",
        agent_version=row.agent_version or "",
        status=row.status or "offline",
        last_heartbeat=row.last_heartbeat.isoformat() if row.last_heartbeat else None,
        available_engines=engines if isinstance(engines, list) else [],
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def _job_to_response(job) -> AgentJobQueueItemResponse:
    payload = {}
    metadata = {}
    if job.input_payload:
        try:
            payload = json.loads(job.input_payload)
        except Exception:
            payload = {"messages": []}
    if job.metadata_:
        try:
            metadata = json.loads(job.metadata_)
        except Exception:
            metadata = {}
    return AgentJobQueueItemResponse(
        id=job.id,
        query_id=job.query_id,
        agent_id=job.agent_id or "",
        provider=job.provider,
        model=job.model,
        sdk_type=job.sdk_type,
        endpoint=job.endpoint,
        kind=job.kind,
        engine="",
        input=payload,
        stream=bool(job.stream),
        metadata=metadata if isinstance(metadata, dict) else {},
        attempt_count=job.attempt_count,
    )
