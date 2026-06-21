from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .emotions import analyze_text, safety_message
from .rooms import room_for_analysis
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EmotionAnalysis,
    JoinRoomRequest,
    JoinRoomResponse,
    MessageOut,
    ReportRequest,
    ReportResponse,
    RoomOut,
    SafetyRisk,
    SessionOut,
)
from .websocket_manager import manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="VibeChat API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions", response_model=SessionOut)
def create_session() -> dict[str, str]:
    return database.create_session()


@app.post("/api/emotions/analyze", response_model=AnalyzeResponse)
async def analyze_emotion(payload: AnalyzeRequest) -> AnalyzeResponse:
    session = database.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Anonymous session not found")

    analysis = await analyze_text(payload.text)
    room = None
    if analysis.safety_risk == SafetyRisk.none:
        room = database.ensure_room(room_for_analysis(analysis))
        room.online_count = manager.online_count(room.id)

    analysis_id = database.save_analysis(payload.session_id, payload.text, analysis, room.id if room else None)
    return AnalyzeResponse(
        analysis_id=analysis_id,
        analysis=analysis,
        recommended_room=room,
        safe_to_join=analysis.safety_risk == SafetyRisk.none,
        safety_message=safety_message(analysis.safety_risk) if analysis.safety_risk != SafetyRisk.none else None,
    )


@app.post("/api/rooms/join", response_model=JoinRoomResponse)
def join_room(payload: JoinRoomRequest, request: Request) -> JoinRoomResponse:
    session = database.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Anonymous session not found")
    analysis = database.get_analysis(payload.analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Emotion analysis not found")
    if analysis["session_id"] != payload.session_id:
        raise HTTPException(status_code=403, detail="Analysis does not belong to this session")
    if analysis["safety_risk"] != SafetyRisk.none.value:
        raise HTTPException(status_code=403, detail="This analysis requires safety support instead of a public room")
    if not analysis["room_id"]:
        room = database.ensure_room(room_for_analysis(EmotionAnalysis(**analysis)))
    else:
        room = database.get_room(analysis["room_id"])
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    room.online_count = manager.online_count(room.id)
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{request.url.netloc}/ws/rooms/{room.id}?session_id={payload.session_id}"
    return JoinRoomResponse(
        room=room,
        messages=[MessageOut(**message) for message in database.list_messages(room.id)],
        ws_url=ws_url,
    )


@app.get("/api/rooms", response_model=list[RoomOut])
def list_rooms() -> list[RoomOut]:
    rooms = database.list_rooms()
    for room in rooms:
        room.online_count = manager.online_count(room.id)
    return rooms


@app.post("/api/messages/report", response_model=ReportResponse)
def report_message(payload: ReportRequest) -> ReportResponse:
    session = database.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Anonymous session not found")
    report_id = database.save_report(payload.message_id, payload.session_id, payload.reason)
    return ReportResponse(report_id=report_id, status="recorded")


@app.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str, session_id: str) -> None:
    session = database.get_session(session_id)
    room = database.get_room(room_id)
    if not session or not room:
        await websocket.close(code=1008)
        return

    display_name = session["display_name"]
    await manager.connect(room_id, websocket)
    await manager.broadcast(
        room_id,
        {"type": "presence", "event": "join", "display_name": display_name, "online_count": manager.online_count(room_id)},
    )
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"content": raw}
            content = str(payload.get("content", "")).strip()
            if not content:
                continue
            if len(content) > 1200:
                await websocket.send_json({"type": "error", "message": "消息太长了，先拆成几句说。"})
                continue
            message = database.save_message(room_id, session_id, display_name, content)
            await manager.broadcast(room_id, {"type": "message", "message": message})
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)
        await manager.broadcast(
            room_id,
            {"type": "presence", "event": "leave", "display_name": display_name, "online_count": manager.online_count(room_id)},
        )
