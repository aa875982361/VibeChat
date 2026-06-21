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
from app.rooms import intensity_bucket, match_signature
from app.schemas import EmotionAnalysis, PrimaryEmotion, SafetyRisk, ShareIntent


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


def make_analysis(
    *,
    primary_emotion: PrimaryEmotion,
    secondary_emotions: list[str],
    intensity: int,
    valence: float,
    arousal: float,
    share_intent: ShareIntent,
) -> EmotionAnalysis:
    return EmotionAnalysis(
        primary_emotion=primary_emotion,
        secondary_emotions=secondary_emotions,
        intensity=intensity,
        valence=valence,
        arousal=arousal,
        share_intent=share_intent,
        summary_label="测试情绪",
        safety_risk=SafetyRisk.none,
        empathy_prompt="先把此刻的感受放在这里。",
        status_message="我想找一个同频的地方说说现在的状态。",
    )


def old_room_signature(analysis: EmotionAnalysis) -> str:
    return f"{analysis.primary_emotion.value}-{intensity_bucket(analysis.intensity)}"


SIMULATED_USER_INPUT_CASES = [
    # joy
    ("今天收到好消息，心里很开心", "joy-medium-share-positive-steady-general"),
    ("这周项目顺利结束，想找人分享一下", "joy-medium-share-positive-steady-general"),
    ("下班路上听到喜欢的歌，觉得很快乐", "joy-medium-share-positive-steady-general"),
    ("朋友夸我做得好，心里高兴了一整晚", "joy-medium-share-positive-steady-general"),
    ("今天升职了真的太开心了！！", "joy-high-share-positive-steady-general"),
    ("抽奖中奖，整个人都特别兴奋", "joy-high-share-positive-steady-general"),
    ("家里人说为我骄傲，我觉得非常幸福", "joy-high-share-positive-steady-general"),
    ("方案顺利通过，开心到想说出来", "joy-medium-share-positive-steady-general"),
    ("客户认可方案，感觉好棒", "joy-medium-share-positive-steady-general"),
    ("今天太好了，想大声笑出来", "joy-high-share-positive-steady-general"),
    # gratitude
    ("今天同事帮我收尾，真的很感谢他", "gratitude-medium-share-positive-calm-general"),
    ("被朋友认真听完以后，我心里很感恩", "gratitude-low-share-positive-calm-general"),
    ("这次被帮助让我觉得世界还挺温柔", "gratitude-low-share-positive-calm-general"),
    ("谢谢室友给我留了热饭，心里暖了一下", "gratitude-low-share-positive-calm-general"),
    ("最近遇到很多善意，觉得自己很幸运", "gratitude-low-share-positive-calm-general"),
    ("导师耐心改了我的稿子，我特别感谢", "gratitude-medium-share-positive-calm-general"),
    ("有人在我低谷时拉了我一把，真的感恩", "gratitude-medium-share-positive-calm-general"),
    ("陌生人帮我找回证件，我想说声谢谢", "gratitude-low-share-positive-calm-general"),
    ("家人一直支持我，我觉得很幸运也很安定", "gratitude-medium-share-positive-calm-general"),
    ("朋友记得我的小事，我非常感谢这份在意", "gratitude-high-share-positive-calm-general"),
    # sadness
    ("今天突然很难过，什么都不想解释", "sadness-low-comfort-negative-steady-general"),
    ("看到以前的照片，心里有点伤心", "sadness-low-comfort-negative-steady-general"),
    ("我哭了一晚上，还是觉得心里空空的", "sadness-low-comfort-negative-steady-general"),
    ("分开以后很失落，心里一直缓不过来", "sadness-low-comfort-negative-steady-general"),
    ("这件事让我心碎，也不想让朋友担心", "sadness-low-comfort-negative-steady-fear"),
    ("最近真的很脆弱，一句话就想哭", "sadness-medium-comfort-negative-steady-general"),
    ("计划落空以后，我特别难过", "sadness-medium-comfort-negative-steady-general"),
    ("回家路上突然很伤心", "sadness-low-comfort-negative-steady-general"),
    ("努力很久还是失败，心里很失落", "sadness-low-comfort-negative-steady-general"),
    ("今天崩溃地哭了很久，只想有人听听", "sadness-medium-comfort-negative-steady-general"),
    # anxiety
    ("明天要面试，紧张得睡不着", "anxiety-high-vent-negative-activated-general"),
    ("一直担心结果不好，心跳停不下来", "anxiety-high-vent-negative-activated-fear"),
    ("想到体检报告就害怕，脑子反复转", "anxiety-high-vent-negative-activated-fear"),
    ("消息还没回复，我有点慌", "anxiety-high-vent-negative-activated-general"),
    ("上台前特别紧张，手都在抖", "anxiety-high-vent-negative-activated-general"),
    ("我怕自己做不好，越想越焦虑", "anxiety-high-vent-negative-activated-fear"),
    ("今晚睡不着，脑子一直想明天的事", "anxiety-high-vent-negative-activated-general"),
    ("担心被拒绝，整个人绷得很紧", "anxiety-high-vent-negative-activated-fear"),
    ("害怕计划突然出问题，心里不踏实", "anxiety-high-vent-negative-activated-fear"),
    ("临近汇报非常焦虑，完全放松不下来", "anxiety-high-vent-negative-activated-general"),
    # anger
    ("被同事甩锅真的很生气", "anger-high-vent-negative-activated-general"),
    ("这件事太不公平了，我心里堵得慌", "anger-high-vent-negative-activated-grievance"),
    ("明明不是我的错，却被骂了一顿，很委屈", "anger-high-vent-negative-activated-grievance"),
    ("对方说话很冲，我有点愤怒", "anger-high-vent-negative-activated-general"),
    ("被临时改需求，气死我了", "anger-high-vent-negative-activated-general"),
    ("努力被否定，我真的很生气也很不甘心", "anger-high-vent-negative-activated-general"),
    ("排队被插队，感觉特别生气", "anger-high-vent-negative-activated-general"),
    ("朋友爽约还怪我，我觉得不公平", "anger-high-vent-negative-activated-grievance"),
    ("被误解以后很委屈，也有点生气", "anger-high-vent-negative-activated-grievance"),
    ("领导当众批评我，我心里很生气", "anger-high-vent-negative-activated-general"),
    # loneliness
    ("一个人在外地生病，没人听我说话", "loneliness-low-comfort-negative-calm-general"),
    ("周末醒来特别孤独，房间安静得难受", "loneliness-medium-comfort-negative-calm-general"),
    ("热闹结束以后，我突然觉得很寂寞", "loneliness-low-comfort-negative-calm-general"),
    ("身边很多人，但没人懂我在想什么", "loneliness-low-comfort-negative-calm-general"),
    ("晚上回到房间，只剩自己一个人", "loneliness-low-comfort-negative-calm-general"),
    ("想说话却没人听，心里很空", "loneliness-low-comfort-negative-calm-general"),
    ("朋友圈很热闹，我却觉得没人懂", "loneliness-low-comfort-negative-calm-general"),
    ("搬到新城市后一直很孤独", "loneliness-low-comfort-negative-calm-general"),
    ("今天吃饭一个人，突然有点寂寞", "loneliness-low-comfort-negative-calm-general"),
    ("很多话憋着没人听，感觉很孤单", "loneliness-low-comfort-negative-calm-general"),
    # stress
    ("连续加班好几天，压力太大了", "stress-high-vent-negative-activated-fatigue"),
    ("工作堆在一起，我快累垮了", "stress-medium-vent-negative-activated-fatigue"),
    ("考试临近，压力压得我喘不过气", "stress-medium-vent-negative-activated-fatigue"),
    ("项目 deadline 快到了，整个人很累", "stress-medium-vent-negative-activated-fatigue"),
    ("家里和工作都要顾，感觉撑不住", "stress-high-vent-negative-activated-general"),
    ("最近任务太多，真的压力很大", "stress-high-vent-negative-activated-fatigue"),
    ("开会开到很晚，累得不想说话", "stress-medium-vent-negative-activated-fatigue"),
    ("工作反复返工，我有点撑不住", "stress-high-vent-negative-activated-general"),
    ("考试复习不完，心里压力爆棚", "stress-medium-vent-negative-activated-fatigue"),
    ("每天都在赶进度，身体和脑子都很累", "stress-medium-vent-negative-activated-fatigue"),
    # shame
    ("昨天会上说错话，觉得特别丢脸", "shame-medium-reflect-negative-steady-general"),
    ("想起那件事还是很羞耻", "shame-low-reflect-negative-steady-general"),
    ("发错消息以后，我尴尬到不敢看手机", "shame-low-reflect-negative-steady-general"),
    ("明明答应了却没做到，我很后悔", "shame-low-reflect-negative-steady-general"),
    ("对朋友发火之后，我一直很自责", "shame-low-reflect-negative-steady-general"),
    ("今天表现很糟糕，觉得有点丢脸", "shame-low-reflect-negative-steady-general"),
    ("被指出错误时，我真的很尴尬", "shame-medium-reflect-negative-steady-general"),
    ("做错决定以后，心里很后悔", "shame-low-reflect-negative-steady-general"),
    ("想到自己的反应，觉得特别自责", "shame-medium-reflect-negative-steady-general"),
    ("那句话说出口后，我有点羞耻", "shame-low-reflect-negative-steady-general"),
    # confusion
    ("我不知道该不该离职，脑子很混乱", "confusion-low-reflect-negative-steady-general"),
    ("最近很迷茫，不知道下一步怎么走", "confusion-low-reflect-negative-steady-general"),
    ("两个选择都不确定，我很纠结", "confusion-low-reflect-negative-steady-general"),
    ("事情太多了，我有点搞不清重点", "confusion-medium-reflect-negative-steady-general"),
    ("心里乱乱的，不知道自己想要什么", "confusion-low-reflect-negative-steady-general"),
    ("计划变来变去，我现在很混乱", "confusion-low-reflect-negative-steady-general"),
    ("未来方向很迷茫，越想越乱", "confusion-low-reflect-negative-steady-general"),
    ("我不知道要不要继续这段关系", "confusion-low-reflect-negative-steady-general"),
    ("好多想法打架，纠结到睡不着", "confusion-low-reflect-negative-steady-general"),
    ("今天只是搞不清自己的情绪", "confusion-low-reflect-negative-steady-general"),
    # neutral
    ("今天没什么特别的事，只想安静待会", "neutral-medium-reflect-mixed-calm-general"),
    ("刚下班，想找个地方随便说两句", "neutral-low-reflect-mixed-calm-general"),
    ("午后有点空，想听听别人聊天", "neutral-low-reflect-mixed-calm-general"),
    ("今天状态还算平稳，想慢慢待一会", "neutral-low-reflect-mixed-calm-general"),
    ("现在没有强烈情绪，只是想说说日常", "neutral-low-reflect-mixed-calm-general"),
    ("我在等车，顺手记录一下此刻", "neutral-low-reflect-mixed-calm-general"),
    ("喝完水以后，想安静地坐一会", "neutral-low-reflect-mixed-calm-general"),
    ("今天比较平常，没有特别起伏", "neutral-medium-reflect-mixed-calm-general"),
    ("只是路过这里，想看看大家在聊什么", "neutral-low-reflect-mixed-calm-general"),
    ("此刻很安静，想轻轻说句话", "neutral-low-reflect-mixed-calm-general"),
]


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


def test_simulated_user_input_matching_accuracy() -> None:
    client = TestClient(app)
    mismatches = []

    for index, (text, expected_room_id) in enumerate(SIMULATED_USER_INPUT_CASES, start=1):
        data = analyze_for_text(client, text)
        actual_room_id = data["recommended_room"]["id"]
        if actual_room_id != expected_room_id:
            mismatches.append(
                {
                    "index": index,
                    "text": text,
                    "expected": expected_room_id,
                    "actual": actual_room_id,
                }
            )

    correct = len(SIMULATED_USER_INPUT_CASES) - len(mismatches)
    accuracy = correct / len(SIMULATED_USER_INPUT_CASES)

    assert len(SIMULATED_USER_INPUT_CASES) == 100
    assert accuracy == pytest.approx(1.0), mismatches


def test_matching_signature_uses_intent_valence_arousal_and_secondary_emotions() -> None:
    base = make_analysis(
        primary_emotion=PrimaryEmotion.anxiety,
        secondary_emotions=["担心"],
        intensity=4,
        valence=-0.6,
        arousal=0.8,
        share_intent=ShareIntent.vent,
    )
    different_intent = base.model_copy(update={"share_intent": ShareIntent.listen})
    different_valence = base.model_copy(update={"valence": 0.0})
    different_arousal = base.model_copy(update={"arousal": 0.35})
    different_secondary = base.model_copy(update={"secondary_emotions": ["委屈"]})

    signatures = {
        match_signature(base),
        match_signature(different_intent),
        match_signature(different_valence),
        match_signature(different_arousal),
        match_signature(different_secondary),
    }

    assert len(signatures) == 5
    assert match_signature(base) == "anxiety-high-vent-negative-activated-fear"
    assert old_room_signature(base) == old_room_signature(different_intent)
    assert old_room_signature(base) == old_room_signature(different_valence)
    assert old_room_signature(base) == old_room_signature(different_arousal)
    assert old_room_signature(base) == old_room_signature(different_secondary)


def test_pairwise_matching_accuracy_improves_over_primary_emotion_only_rooms() -> None:
    cases = [
        (
            "anxiety-vent-fear",
            make_analysis(
                primary_emotion=PrimaryEmotion.anxiety,
                secondary_emotions=["担心"],
                intensity=4,
                valence=-0.6,
                arousal=0.8,
                share_intent=ShareIntent.vent,
            ),
        ),
        (
            "anxiety-vent-fear",
            make_analysis(
                primary_emotion=PrimaryEmotion.anxiety,
                secondary_emotions=["害怕"],
                intensity=4,
                valence=-0.58,
                arousal=0.78,
                share_intent=ShareIntent.vent,
            ),
        ),
        (
            "anxiety-listen-fear",
            make_analysis(
                primary_emotion=PrimaryEmotion.anxiety,
                secondary_emotions=["担心"],
                intensity=4,
                valence=-0.6,
                arousal=0.8,
                share_intent=ShareIntent.listen,
            ),
        ),
        (
            "anxiety-vent-calm-fear",
            make_analysis(
                primary_emotion=PrimaryEmotion.anxiety,
                secondary_emotions=["担心"],
                intensity=4,
                valence=-0.6,
                arousal=0.35,
                share_intent=ShareIntent.vent,
            ),
        ),
        (
            "anxiety-vent-mixed-fear",
            make_analysis(
                primary_emotion=PrimaryEmotion.anxiety,
                secondary_emotions=["担心"],
                intensity=4,
                valence=0.0,
                arousal=0.8,
                share_intent=ShareIntent.vent,
            ),
        ),
        (
            "anxiety-vent-grievance",
            make_analysis(
                primary_emotion=PrimaryEmotion.anxiety,
                secondary_emotions=["委屈"],
                intensity=4,
                valence=-0.6,
                arousal=0.8,
                share_intent=ShareIntent.vent,
            ),
        ),
        (
            "anger-vent-grievance",
            make_analysis(
                primary_emotion=PrimaryEmotion.anger,
                secondary_emotions=["委屈"],
                intensity=4,
                valence=-0.54,
                arousal=0.82,
                share_intent=ShareIntent.vent,
            ),
        ),
        (
            "anger-vent-grievance",
            make_analysis(
                primary_emotion=PrimaryEmotion.anger,
                secondary_emotions=["不公平"],
                intensity=4,
                valence=-0.5,
                arousal=0.8,
                share_intent=ShareIntent.vent,
            ),
        ),
    ]

    total_pairs = 0
    old_correct = 0
    new_correct = 0
    for index, (expected_group, analysis) in enumerate(cases):
        for other_expected_group, other_analysis in cases[index + 1 :]:
            should_match = expected_group == other_expected_group
            old_matches = old_room_signature(analysis) == old_room_signature(other_analysis)
            new_matches = match_signature(analysis) == match_signature(other_analysis)
            total_pairs += 1
            old_correct += old_matches == should_match
            new_correct += new_matches == should_match

    old_accuracy = old_correct / total_pairs
    new_accuracy = new_correct / total_pairs

    assert old_accuracy == pytest.approx(0.5)
    assert new_accuracy == pytest.approx(1.0)


def test_similar_users_match_the_same_emotion_intensity_room() -> None:
    client = TestClient(app)
    first = analyze_for_text(client, "今天升职了真的太开心了！！")
    second = analyze_for_text(client, "项目终于上线了，太好了，开心到想找人分享！！")

    assert first["analysis"]["primary_emotion"] == "joy"
    assert second["analysis"]["primary_emotion"] == "joy"
    assert first["recommended_room"]["id"] == second["recommended_room"]["id"]
    assert first["recommended_room"]["id"] == "joy-high-share-positive-steady-general"


def test_different_intensity_creates_a_separate_room_within_same_emotion() -> None:
    client = TestClient(app)
    calm = analyze_for_text(client, "今天挺开心")
    intense = analyze_for_text(client, "今天升职了真的太开心了！！")

    assert calm["analysis"]["primary_emotion"] == intense["analysis"]["primary_emotion"] == "joy"
    assert calm["recommended_room"]["id"] == "joy-medium-share-positive-steady-general"
    assert intense["recommended_room"]["id"] == "joy-high-share-positive-steady-general"
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
