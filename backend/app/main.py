from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Optional

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
    RejoinRoomRequest,
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
    allow_origins=["*"],
    allow_credentials=False,
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
        room = database.get_room(room.id, payload.session_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
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

    database.add_room_membership(payload.session_id, room.id)
    room = database.get_room(room.id, payload.session_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return room_response(room, payload.session_id, request)


@app.post("/api/rooms/rejoin", response_model=JoinRoomResponse)
def rejoin_room(payload: RejoinRoomRequest, request: Request) -> JoinRoomResponse:
    session = database.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Anonymous session not found")
    if not database.is_room_member(payload.session_id, payload.room_id):
        raise HTTPException(status_code=403, detail="Public rooms can only be entered through matching")
    room = database.get_room(payload.room_id, payload.session_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return room_response(room, payload.session_id, request)


def room_response(room: RoomOut, session_id: str, request: Request) -> JoinRoomResponse:
    room.online_count = manager.online_count(room.id)
    scheme = websocket_scheme(request)
    host = forwarded_header(request, "x-forwarded-host") or request.url.netloc
    ws_url = f"{scheme}://{host}/ws/rooms/{room.id}?session_id={session_id}"
    return JoinRoomResponse(
        room=room,
        messages=[MessageOut(**message) for message in database.list_messages(room.id)],
        ws_url=ws_url,
    )


def forwarded_header(request: Request, name: str) -> Optional[str]:
    value = request.headers.get(name)
    if not value:
        return None
    return value.split(",", 1)[0].strip() or None


def websocket_scheme(request: Request) -> str:
    forwarded_proto = forwarded_header(request, "x-forwarded-proto")
    scheme = forwarded_proto or request.url.scheme
    return "wss" if scheme in {"https", "wss"} else "ws"


@app.get("/api/rooms", response_model=list[RoomOut])
def list_rooms(session_id: Optional[str] = None) -> list[RoomOut]:
    if session_id and not database.get_session(session_id):
        raise HTTPException(status_code=404, detail="Anonymous session not found")
    rooms = database.list_rooms(session_id)
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
    current_room = database.get_room(room_id, session_id)
    participant_count = current_room.participant_count if current_room else 0
    await manager.broadcast(
        room_id,
        {
            "type": "presence",
            "event": "join",
            "display_name": display_name,
            "online_count": manager.online_count(room_id),
            "participant_count": participant_count,
        },
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
            {
                "type": "presence",
                "event": "leave",
                "display_name": display_name,
                "online_count": manager.online_count(room_id),
                "participant_count": participant_count,
            },
        )
