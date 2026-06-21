from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PrimaryEmotion(str, Enum):
    joy = "joy"
    sadness = "sadness"
    anxiety = "anxiety"
    anger = "anger"
    loneliness = "loneliness"
    stress = "stress"
    gratitude = "gratitude"
    shame = "shame"
    confusion = "confusion"
    neutral = "neutral"


class ShareIntent(str, Enum):
    celebrate = "celebrate"
    vent = "vent"
    seek_comfort = "seek_comfort"
    listen = "listen"
    reflect = "reflect"


class SafetyRisk(str, Enum):
    none = "none"
    self_harm = "self_harm"
    violence = "violence"
    severe_distress = "severe_distress"


class SessionOut(BaseModel):
    session_id: str
    display_name: str


class AnalyzeRequest(BaseModel):
    session_id: str
    text: str = Field(min_length=2, max_length=2000)


class EmotionAnalysis(BaseModel):
    primary_emotion: PrimaryEmotion
    secondary_emotions: list[str] = Field(default_factory=list)
    intensity: int = Field(ge=1, le=5)
    valence: float = Field(ge=-1, le=1)
    arousal: float = Field(ge=0, le=1)
    share_intent: ShareIntent
    summary_label: str = Field(min_length=1, max_length=24)
    safety_risk: SafetyRisk = SafetyRisk.none
    empathy_prompt: str = Field(min_length=1, max_length=160)
    status_message: str = Field(min_length=1, max_length=180)


class RoomOut(BaseModel):
    id: str
    primary_emotion: PrimaryEmotion
    intensity_bucket: str
    name: str
    description: str
    online_count: int = 0
    participant_count: int = 0
    joined_by_me: bool = False


class AnalyzeResponse(BaseModel):
    analysis_id: str
    analysis: EmotionAnalysis
    recommended_room: Optional[RoomOut] = None
    safe_to_join: bool
    safety_message: Optional[str] = None


class JoinRoomRequest(BaseModel):
    session_id: str
    analysis_id: str


class RejoinRoomRequest(BaseModel):
    session_id: str
    room_id: str


class MessageOut(BaseModel):
    id: str
    room_id: str
    session_id: str
    display_name: str
    content: str
    safety_status: str = "ok"
    created_at: str


class JoinRoomResponse(BaseModel):
    room: RoomOut
    messages: list[MessageOut]
    ws_url: str


class ReportRequest(BaseModel):
    session_id: str
    message_id: str
    reason: str = Field(min_length=2, max_length=500)


class ReportResponse(BaseModel):
    report_id: str
    status: str
