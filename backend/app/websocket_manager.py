from __future__ import annotations

import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, room_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active[room_id].add(websocket)

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        self.active[room_id].discard(websocket)
        if not self.active[room_id]:
            self.active.pop(room_id, None)

    def online_count(self, room_id: str) -> int:
        return len(self.active.get(room_id, set()))

    async def broadcast(self, room_id: str, payload: dict) -> None:
        stale: list[WebSocket] = []
        message = json.dumps(payload, ensure_ascii=False)
        for websocket in self.active.get(room_id, set()).copy():
            try:
                await websocket.send_text(message)
            except RuntimeError:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(room_id, websocket)


manager = ConnectionManager()

