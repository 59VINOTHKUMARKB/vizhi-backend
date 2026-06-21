"""In-memory agent websocket manager."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class _AgentSocket:
    websocket: WebSocket
    lock: asyncio.Lock


class AgentWebSocketManager:
    def __init__(self) -> None:
        self._sockets: dict[str, _AgentSocket] = {}

    async def connect(self, agent_id: str, websocket: WebSocket) -> None:
        self._sockets[agent_id] = _AgentSocket(websocket=websocket, lock=asyncio.Lock())

    async def disconnect(self, agent_id: str) -> None:
        self._sockets.pop(agent_id, None)

    async def notify(self, agent_id: str, message: dict) -> None:
        socket = self._sockets.get(agent_id)
        if not socket:
            return
        async with socket.lock:
            try:
                await socket.websocket.send_text(json.dumps(message))
            except Exception:
                await self.disconnect(agent_id)


agent_ws_manager = AgentWebSocketManager()
