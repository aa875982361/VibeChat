import asyncio
import json
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import database
from app import emotions
from app.main import app


def setup_function() -> None:
    database.reset_db_for_tests("/tmp/vibechat-test.db")
    os.environ["AI_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""


def test_create_session_and_analyze_joy_room() -> None:
    client = TestClient(app)
    session = client.post("/api/sessions").json()

    response = client.post(
        "/api/emotions/analyze",
        json={"session_id": session["session_id"], "text": "今天升职了但不敢发朋友圈，怕别人觉得我炫耀"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["safe_to_join"] is True
    assert data["analysis"]["primary_emotion"] == "joy"
    assert "AI 识别" not in data["analysis"]["status_message"]
    assert "升职" in data["analysis"]["status_message"]
    assert data["recommended_room"]["id"].startswith("joy-")


def test_sadness_maps_to_support_room() -> None:
    client = TestClient(app)
    session = client.post("/api/sessions").json()

    response = client.post(
        "/api/emotions/analyze",
        json={"session_id": session["session_id"], "text": "我很难过但不想朋友担心，也不想让大家看到我的脆弱"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["analysis"]["primary_emotion"] == "sadness"
    assert data["analysis"]["share_intent"] == "seek_comfort"
    assert "陪伴" in data["recommended_room"]["name"]


def test_risk_content_does_not_join_public_room() -> None:
    client = TestClient(app)
    session = client.post("/api/sessions").json()
    analyzed = client.post(
        "/api/emotions/analyze",
        json={"session_id": session["session_id"], "text": "我不想活了，想结束生命"},
    ).json()

    assert analyzed["safe_to_join"] is False
    assert analyzed["recommended_room"] is None
    join = client.post(
        "/api/rooms/join",
        json={"session_id": session["session_id"], "analysis_id": analyzed["analysis_id"]},
    )
    assert join.status_code == 403


def test_join_room_and_websocket_message_broadcast() -> None:
    client = TestClient(app)
    session = client.post("/api/sessions").json()
    analyzed = client.post(
        "/api/emotions/analyze",
        json={"session_id": session["session_id"], "text": "今天升职了真的很开心"},
    ).json()

    joined = client.post(
        "/api/rooms/join",
        json={"session_id": session["session_id"], "analysis_id": analyzed["analysis_id"]},
    )

    assert joined.status_code == 200
    room_id = joined.json()["room"]["id"]
    with client.websocket_connect(f"/ws/rooms/{room_id}?session_id={session['session_id']}") as websocket:
        websocket.receive_json()
        websocket.send_json({"content": "我也想把这份开心说出来"})
        event = websocket.receive_json()
        assert event["type"] == "message"
        assert event["message"]["content"] == "我也想把这份开心说出来"


def test_join_room_ws_url_respects_forwarded_https_headers() -> None:
    client = TestClient(app)
    session = client.post("/api/sessions").json()
    analyzed = client.post(
        "/api/emotions/analyze",
        json={"session_id": session["session_id"], "text": "今天升职了真的很开心"},
    ).json()

    joined = client.post(
        "/api/rooms/join",
        json={"session_id": session["session_id"], "analysis_id": analyzed["analysis_id"]},
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "vibechat.nisonfuture.cn"},
    )

    assert joined.status_code == 200
    assert joined.json()["ws_url"].startswith("wss://vibechat.nisonfuture.cn/ws/rooms/")


def test_rooms_are_rejoinable_only_after_matching_join() -> None:
    client = TestClient(app)
    first_session = client.post("/api/sessions").json()
    second_session = client.post("/api/sessions").json()

    analyzed = client.post(
        "/api/emotions/analyze",
        json={"session_id": first_session["session_id"], "text": "今天升职了真的很开心"},
    ).json()
    room_id = analyzed["recommended_room"]["id"]

    second_rooms = client.get(f"/api/rooms?session_id={second_session['session_id']}").json()
    public_room = next(room for room in second_rooms if room["id"] == room_id)
    assert public_room["joined_by_me"] is False
    assert public_room["participant_count"] == 0

    blocked = client.post(
        "/api/rooms/rejoin",
        json={"session_id": second_session["session_id"], "room_id": room_id},
    )
    assert blocked.status_code == 403

    joined = client.post(
        "/api/rooms/join",
        json={"session_id": first_session["session_id"], "analysis_id": analyzed["analysis_id"]},
    ).json()
    assert joined["room"]["joined_by_me"] is True
    assert joined["room"]["participant_count"] == 1

    rejoined = client.post(
        "/api/rooms/rejoin",
        json={"session_id": first_session["session_id"], "room_id": room_id},
    ).json()
    assert rejoined["room"]["joined_by_me"] is True
    assert rejoined["room"]["participant_count"] == 1

    first_rooms = client.get(f"/api/rooms?session_id={first_session['session_id']}").json()
    my_room = next(room for room in first_rooms if room["id"] == room_id)
    assert my_room["joined_by_me"] is True
    assert my_room["participant_count"] == 1

    second_analyzed = client.post(
        "/api/emotions/analyze",
        json={"session_id": second_session["session_id"], "text": "今天升职了真的很开心"},
    ).json()
    assert second_analyzed["recommended_room"]["id"] == room_id
    second_joined = client.post(
        "/api/rooms/join",
        json={"session_id": second_session["session_id"], "analysis_id": second_analyzed["analysis_id"]},
    ).json()
    assert second_joined["room"]["participant_count"] == 2


def test_anthropic_provider_uses_messages_api(monkeypatch) -> None:
    calls = {}

    class FakeMessages:
        async def create(self, **kwargs):
            calls.update(kwargs)
            payload = {
                "primary_emotion": "anxiety",
                "secondary_emotions": ["担心"],
                "intensity": 4,
                "valence": -0.6,
                "arousal": 0.8,
                "share_intent": "vent",
                "summary_label": "紧绷的焦虑",
                "safety_risk": "none",
                "empathy_prompt": "先把这口气慢慢放下来。",
                "status_message": "我现在有点紧张，想找个地方把这份担心说出来。",
            }
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))])

    class FakeAnthropic:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.messages = FakeMessages()

    monkeypatch.setattr(emotions, "AsyncAnthropic", FakeAnthropic)
    os.environ["AI_PROVIDER"] = "anthropic"
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ["ANTHROPIC_MODEL"] = "claude-sonnet-4-6"

    analysis = asyncio.run(emotions.analyze_text("我明天要面试，紧张得睡不着"))

    assert calls["client_kwargs"]["api_key"] == "test-key"
    assert calls["model"] == "claude-sonnet-4-6"
    assert analysis.primary_emotion == "anxiety"
    assert analysis.intensity == 4
