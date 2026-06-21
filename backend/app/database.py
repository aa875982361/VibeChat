from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import settings
from .schemas import EmotionAnalysis, RoomOut


ADJECTIVES = ["雾蓝", "月白", "松风", "晴川", "微光", "星芒", "暖橙", "青柠", "云影", "静海"]
NOUNS = ["旅人", "听筒", "纸船", "回声", "信号", "灯塔", "雨伞", "便签", "小站", "风铃"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path() -> str:
    path = settings.db_path
    if path.startswith("./"):
        path = str(Path(__file__).resolve().parents[2] / path[2:])
    return path


def connection() -> sqlite3.Connection:
    path = db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS anonymous_users (
                session_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                primary_emotion TEXT NOT NULL,
                intensity_bucket TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS emotion_analyses (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                original_text TEXT NOT NULL,
                primary_emotion TEXT NOT NULL,
                secondary_emotions TEXT NOT NULL,
                intensity INTEGER NOT NULL,
                valence REAL NOT NULL,
                arousal REAL NOT NULL,
                share_intent TEXT NOT NULL,
                summary_label TEXT NOT NULL,
                safety_risk TEXT NOT NULL,
                empathy_prompt TEXT NOT NULL,
                room_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES anonymous_users(session_id),
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                content TEXT NOT NULL,
                safety_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id),
                FOREIGN KEY(session_id) REFERENCES anonymous_users(session_id)
            );

            CREATE TABLE IF NOT EXISTS message_reports (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id),
                FOREIGN KEY(session_id) REFERENCES anonymous_users(session_id)
            );
            """
        )


def make_display_name() -> str:
    return f"{secrets.choice(ADJECTIVES)}{secrets.choice(NOUNS)}-{secrets.randbelow(9000) + 1000}"


def create_session() -> dict[str, str]:
    session_id = str(uuid.uuid4())
    display_name = make_display_name()
    with connection() as conn:
        conn.execute(
            "INSERT INTO anonymous_users (session_id, display_name, created_at) VALUES (?, ?, ?)",
            (session_id, display_name, now_iso()),
        )
    return {"session_id": session_id, "display_name": display_name}


def get_session(session_id: str) -> Optional[sqlite3.Row]:
    with connection() as conn:
        return conn.execute(
            "SELECT session_id, display_name, created_at FROM anonymous_users WHERE session_id = ?",
            (session_id,),
        ).fetchone()


def ensure_room(room: RoomOut) -> RoomOut:
    with connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO rooms (id, primary_emotion, intensity_bucket, name, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                room.id,
                room.primary_emotion.value,
                room.intensity_bucket,
                room.name,
                room.description,
                now_iso(),
            ),
        )
    return room


def get_room(room_id: str) -> Optional[RoomOut]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return room_from_row(row) if row else None


def list_rooms() -> list[RoomOut]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM rooms ORDER BY created_at DESC").fetchall()
    return [room_from_row(row) for row in rows]


def room_from_row(row: sqlite3.Row) -> RoomOut:
    return RoomOut(
        id=row["id"],
        primary_emotion=row["primary_emotion"],
        intensity_bucket=row["intensity_bucket"],
        name=row["name"],
        description=row["description"],
        online_count=0,
    )


def save_analysis(session_id: str, original_text: str, analysis: EmotionAnalysis, room_id: Optional[str]) -> str:
    analysis_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO emotion_analyses (
                id, session_id, original_text, primary_emotion, secondary_emotions, intensity,
                valence, arousal, share_intent, summary_label, safety_risk, empathy_prompt,
                room_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                session_id,
                original_text,
                analysis.primary_emotion.value,
                json.dumps(analysis.secondary_emotions, ensure_ascii=False),
                analysis.intensity,
                analysis.valence,
                analysis.arousal,
                analysis.share_intent.value,
                analysis.summary_label,
                analysis.safety_risk.value,
                analysis.empathy_prompt,
                room_id,
                now_iso(),
            ),
        )
    return analysis_id


def get_analysis(analysis_id: str) -> Optional[dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM emotion_analyses WHERE id = ?", (analysis_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["secondary_emotions"] = json.loads(data["secondary_emotions"])
    return data


def save_message(room_id: str, session_id: str, display_name: str, content: str, safety_status: str = "ok") -> dict[str, Any]:
    message = {
        "id": str(uuid.uuid4()),
        "room_id": room_id,
        "session_id": session_id,
        "display_name": display_name,
        "content": content,
        "safety_status": safety_status,
        "created_at": now_iso(),
    }
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (id, room_id, session_id, display_name, content, safety_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message["id"],
                message["room_id"],
                message["session_id"],
                message["display_name"],
                message["content"],
                message["safety_status"],
                message["created_at"],
            ),
        )
    return message


def list_messages(room_id: str, limit: int = 80) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM messages
            WHERE room_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (room_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def save_report(message_id: str, session_id: str, reason: str) -> str:
    report_id = str(uuid.uuid4())
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO message_reports (id, message_id, session_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (report_id, message_id, session_id, reason, now_iso()),
        )
    return report_id


def reset_db_for_tests(path: str) -> None:
    os.environ["VIBECHAT_DB_PATH"] = path
    if Path(path).exists():
        Path(path).unlink()
    init_db()

