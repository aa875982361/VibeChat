import os

from fastapi.testclient import TestClient

from app import database
from app.main import app


def setup_function() -> None:
    database.reset_db_for_tests("/tmp/vibechat-test.db")
    os.environ["OPENAI_API_KEY"] = ""


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

