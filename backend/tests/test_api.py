import asyncio
import json
import os
from types import SimpleNamespace
from typing import Optional

import pytest
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


def analyze_for_text(client: TestClient, text: str) -> dict:
    session = client.post("/api/sessions").json()
    response = client.post(
        "/api/emotions/analyze",
        json={"session_id": session["session_id"], "text": text},
    )
    assert response.status_code == 200
    return response.json()


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


@pytest.mark.parametrize(
    (
        "text",
        "expected_emotion",
        "expected_intent",
        "expected_room_prefix",
        "expected_room_word",
        "expected_valence",
        "expected_secondary",
    ),
    [
        (
            "明天要面试，紧张得睡不着，脑子一直停不下来",
            "anxiety",
            "vent",
            "anxiety-",
            "焦虑",
            "negative",
            None,
        ),
        (
            "连续加班好几天，压力太大了，真的累到不想说话",
            "stress",
            "vent",
            "stress-",
            "压力",
            "negative",
            "疲惫",
        ),
        (
            "一个人在外地生病，没人懂，也没人听我说话",
            "loneliness",
            "seek_comfort",
            "loneliness-",
            "孤独",
            "negative",
            None,
        ),
        (
            "朋友帮我解决了大麻烦，真的很感谢，也觉得自己很幸运",
            "gratitude",
            "celebrate",
            "gratitude-",
            "暖光",
            "positive",
            None,
        ),
        (
            "昨天会上说错话，觉得特别丢脸，很后悔也有点自责",
            "shame",
            "reflect",
            "shame-",
            "柔软",
            "negative",
            None,
        ),
        (
            "我不知道该不该离职，脑子很混乱，纠结到搞不清方向",
            "confusion",
            "reflect",
            "confusion-",
            "混乱",
            "negative",
            None,
        ),
        (
            "被同事甩锅真的很生气，觉得太不公平了",
            "anger",
            "vent",
            "anger-",
            "降温",
            "negative",
            "委屈",
        ),
    ],
)
def test_user_input_scenarios_map_to_reasonable_rooms(
    text: str,
    expected_emotion: str,
    expected_intent: str,
    expected_room_prefix: str,
    expected_room_word: str,
    expected_valence: str,
    expected_secondary: Optional[str],
) -> None:
    client = TestClient(app)

    data = analyze_for_text(client, text)
    analysis = data["analysis"]
    room = data["recommended_room"]

    assert data["safe_to_join"] is True
    assert analysis["primary_emotion"] == expected_emotion
    assert analysis["share_intent"] == expected_intent
    assert room["id"].startswith(expected_room_prefix)
    assert expected_room_word in room["name"]
    assert 1 <= analysis["intensity"] <= 5
    assert 0 <= analysis["arousal"] <= 1
    assert "AI" not in analysis["status_message"]
    assert analysis["status_message"].startswith(text[: min(len(text), 18)])
    if expected_valence == "positive":
        assert analysis["valence"] > 0
    else:
        assert analysis["valence"] < 0
    if expected_secondary:
        assert expected_secondary in analysis["secondary_emotions"]


def test_similar_users_match_the_same_emotion_intensity_room() -> None:
    client = TestClient(app)
    first = analyze_for_text(client, "今天升职了真的太开心了！！")
    second = analyze_for_text(client, "项目终于上线了，太好了，开心到想找人分享！！")

    assert first["analysis"]["primary_emotion"] == "joy"
    assert second["analysis"]["primary_emotion"] == "joy"
    assert first["recommended_room"]["id"] == second["recommended_room"]["id"]
    assert first["recommended_room"]["id"] == "joy-high"


def test_different_intensity_creates_a_separate_room_within_same_emotion() -> None:
    client = TestClient(app)
    calm = analyze_for_text(client, "今天挺开心")
    intense = analyze_for_text(client, "今天升职了真的太开心了！！")

    assert calm["analysis"]["primary_emotion"] == intense["analysis"]["primary_emotion"] == "joy"
    assert calm["recommended_room"]["id"] == "joy-medium"
    assert intense["recommended_room"]["id"] == "joy-high"
    assert calm["recommended_room"]["id"] != intense["recommended_room"]["id"]


@pytest.mark.parametrize(
    ("text", "expected_risk"),
    [
        ("我不想活了，想结束生命", "self_harm"),
        ("我想报复他，真的想伤害别人", "violence"),
        ("我彻底崩溃了，觉得没有希望", "severe_distress"),
    ],
)
def test_high_risk_user_inputs_are_not_matched_into_public_rooms(text: str, expected_risk: str) -> None:
    client = TestClient(app)

    data = analyze_for_text(client, text)

    assert data["safe_to_join"] is False
    assert data["recommended_room"] is None
    assert data["analysis"]["safety_risk"] == expected_risk
    assert data["safety_message"]


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
