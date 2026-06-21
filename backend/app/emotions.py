from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from .config import settings
from .schemas import EmotionAnalysis, PrimaryEmotion, SafetyRisk, ShareIntent


EMOTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "primary_emotion",
        "secondary_emotions",
        "intensity",
        "valence",
        "arousal",
        "share_intent",
        "summary_label",
        "safety_risk",
        "empathy_prompt",
    ],
    "properties": {
        "primary_emotion": {"type": "string", "enum": [item.value for item in PrimaryEmotion]},
        "secondary_emotions": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "intensity": {"type": "integer", "minimum": 1, "maximum": 5},
        "valence": {"type": "number", "minimum": -1, "maximum": 1},
        "arousal": {"type": "number", "minimum": 0, "maximum": 1},
        "share_intent": {"type": "string", "enum": [item.value for item in ShareIntent]},
        "summary_label": {"type": "string", "minLength": 1, "maxLength": 24},
        "safety_risk": {"type": "string", "enum": [item.value for item in SafetyRisk]},
        "empathy_prompt": {"type": "string", "minLength": 1, "maxLength": 160},
    },
}


SYSTEM_PROMPT = """
你是 VibeChat 的情绪识别器。请只分析用户当下文字中的情绪，不做诊断。
目标是帮助用户进入匿名情绪聊天室。返回 JSON 必须符合 schema。
判断 primary_emotion、复合 secondary_emotions、强度、正负倾向、唤醒度和分享意图。
如果文本表达自伤、自杀、伤害他人或极端失控风险，设置 safety_risk。
empathy_prompt 用中文，克制、温柔，不像心理咨询广告，不超过 60 个汉字。
"""


async def analyze_text(text: str) -> EmotionAnalysis:
    if not settings.openai_api_key:
        return fallback_analysis(text)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    moderation_risk = await moderate_text(client, text)
    response = await client.responses.create(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "emotion_analysis",
                "schema": EMOTION_SCHEMA,
                "strict": True,
            }
        },
    )
    payload = json.loads(response.output_text)
    analysis = EmotionAnalysis(**payload)
    if moderation_risk != SafetyRisk.none:
        analysis.safety_risk = moderation_risk
    return analysis


async def moderate_text(client: AsyncOpenAI, text: str) -> SafetyRisk:
    result = await client.moderations.create(model=settings.openai_moderation_model, input=text)
    first = result.results[0].model_dump()
    categories = first.get("categories", {})
    if categories.get("self-harm/intent") or categories.get("self-harm/instructions") or categories.get("self-harm"):
        return SafetyRisk.self_harm
    if categories.get("violence") or categories.get("violence/graphic") or categories.get("harassment/threatening"):
        return SafetyRisk.violence
    return SafetyRisk.none


def fallback_analysis(text: str) -> EmotionAnalysis:
    lowered = text.lower()
    risk = fallback_safety(text)
    emotion = PrimaryEmotion.neutral
    intent = ShareIntent.reflect
    valence = 0.0
    arousal = 0.35
    label = "情绪待整理"

    if has_any(text, ["开心", "高兴", "快乐", "升职", "中奖", "好棒", "顺利", "幸福", "太好了"]):
        emotion = PrimaryEmotion.joy
        intent = ShareIntent.celebrate
        valence = 0.82
        arousal = 0.65
        label = "想分享的开心"
    if has_any(text, ["感谢", "感恩", "被帮助", "谢谢", "幸运"]):
        emotion = PrimaryEmotion.gratitude
        intent = ShareIntent.celebrate
        valence = 0.75
        arousal = 0.45
        label = "被照亮的感谢"
    if has_any(text, ["难过", "伤心", "哭", "崩溃", "失落", "心碎", "脆弱"]):
        emotion = PrimaryEmotion.sadness
        intent = ShareIntent.seek_comfort
        valence = -0.72
        arousal = 0.5
        label = "需要被接住的难过"
    if has_any(text, ["焦虑", "担心", "害怕", "慌", "紧张", "睡不着"]) and emotion not in {
        PrimaryEmotion.sadness,
        PrimaryEmotion.joy,
        PrimaryEmotion.gratitude,
    }:
        emotion = PrimaryEmotion.anxiety
        intent = ShareIntent.vent
        valence = -0.58
        arousal = 0.78
        label = "紧绷的焦虑"
    if has_any(text, ["生气", "愤怒", "气死", "委屈", "不公平"]):
        emotion = PrimaryEmotion.anger
        intent = ShareIntent.vent
        valence = -0.54
        arousal = 0.82
        label = "需要出口的生气"
    if has_any(text, ["孤独", "一个人", "没人懂", "寂寞", "没人听"]):
        emotion = PrimaryEmotion.loneliness
        intent = ShareIntent.seek_comfort
        valence = -0.65
        arousal = 0.38
        label = "想被听见的孤独"
    if has_any(text, ["压力", "累", "撑不住", "加班", "考试", "工作"]):
        emotion = PrimaryEmotion.stress
        intent = ShareIntent.vent
        valence = -0.5
        arousal = 0.72
        label = "正在超载的压力"
    if has_any(text, ["丢脸", "羞耻", "后悔", "尴尬", "自责"]):
        emotion = PrimaryEmotion.shame
        intent = ShareIntent.reflect
        valence = -0.62
        arousal = 0.48
        label = "不好开口的自责"
    if has_any(text, ["不知道", "混乱", "迷茫", "纠结", "搞不清"]):
        emotion = PrimaryEmotion.confusion
        intent = ShareIntent.reflect
        valence = -0.25
        arousal = 0.52
        label = "还没理清的混乱"

    intensity = infer_intensity(text, arousal)
    secondaries = infer_secondaries(text, emotion)
    if risk != SafetyRisk.none:
        label = "需要先保证安全"
        intent = ShareIntent.seek_comfort

    return EmotionAnalysis(
        primary_emotion=emotion,
        secondary_emotions=secondaries,
        intensity=intensity,
        valence=valence,
        arousal=arousal,
        share_intent=intent,
        summary_label=label,
        safety_risk=risk,
        empathy_prompt=empathy_for(emotion, risk),
    )


def has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def fallback_safety(text: str) -> SafetyRisk:
    self_harm = ["自杀", "轻生", "不想活", "结束生命", "伤害自己", "割腕", "跳楼", "活不下去"]
    violence = ["杀了", "弄死", "伤害别人", "报复他", "打死"]
    severe = ["撑不住了", "彻底崩溃", "没有希望", "绝望"]
    if has_any(text, self_harm):
        return SafetyRisk.self_harm
    if has_any(text, violence):
        return SafetyRisk.violence
    if has_any(text, severe):
        return SafetyRisk.severe_distress
    return SafetyRisk.none


def infer_intensity(text: str, arousal: float) -> int:
    score = 3
    if arousal > 0.75:
        score += 1
    if re.search(r"[!！]{2,}|太|非常|真的|特别|崩溃|撑不住|气死", text):
        score += 1
    if len(text) < 18 and arousal < 0.55:
        score -= 1
    return max(1, min(score, 5))


def infer_secondaries(text: str, primary: PrimaryEmotion) -> list[str]:
    candidates: list[tuple[str, list[str]]] = [
        ("委屈", ["委屈", "不公平"]),
        ("害怕", ["害怕", "怕", "担心"]),
        ("期待", ["期待", "希望"]),
        ("羞耻", ["丢脸", "羞耻", "尴尬"]),
        ("孤独", ["孤独", "没人懂", "一个人"]),
        ("开心", ["开心", "快乐", "高兴"]),
        ("疲惫", ["累", "疲惫", "压力"]),
    ]
    found = [name for name, words in candidates if has_any(text, words)]
    primary_cn = {
        PrimaryEmotion.joy: "开心",
        PrimaryEmotion.sadness: "难过",
        PrimaryEmotion.anxiety: "焦虑",
        PrimaryEmotion.anger: "生气",
        PrimaryEmotion.loneliness: "孤独",
        PrimaryEmotion.stress: "压力",
        PrimaryEmotion.gratitude: "感谢",
        PrimaryEmotion.shame: "羞耻",
        PrimaryEmotion.confusion: "混乱",
        PrimaryEmotion.neutral: "平静",
    }[primary]
    return [item for item in found if item != primary_cn][:4]


def empathy_for(emotion: PrimaryEmotion, risk: SafetyRisk) -> str:
    if risk == SafetyRisk.self_harm:
        return "你现在不需要一个人扛着。先离开危险物品，联系身边可信的人或当地紧急求助。"
    if risk == SafetyRisk.violence:
        return "先让自己和他人保持距离，暂停行动，联系可信的人或当地紧急服务。"
    if risk == SafetyRisk.severe_distress:
        return "这份崩溃值得被认真对待。先找一个真实的人陪你待一会。"
    return {
        PrimaryEmotion.joy: "这份开心可以被单纯地分享，不需要先证明自己没有炫耀。",
        PrimaryEmotion.gratitude: "被善意接住的瞬间，值得有个地方轻轻放大。",
        PrimaryEmotion.sadness: "你可以先难过，不必马上解释，也不必怕麻烦别人。",
        PrimaryEmotion.anxiety: "紧绷不是你的错，我们先把这口气慢慢放下来。",
        PrimaryEmotion.anger: "生气里也许有很重要的边界，先把它说出来。",
        PrimaryEmotion.loneliness: "没人懂的感觉很重，这里至少先有人听见。",
        PrimaryEmotion.stress: "撑太久的人，也需要一个不用表现得很好的地方。",
        PrimaryEmotion.shame: "那些难以启齿的部分，也可以被温柔地放在这里。",
        PrimaryEmotion.confusion: "理不清也没关系，先从一个句子开始。",
        PrimaryEmotion.neutral: "此刻没有强烈情绪，也可以拥有一个安静的连接。",
    }[emotion]


def safety_message(risk: SafetyRisk) -> str:
    if risk == SafetyRisk.self_harm:
        return "如果你可能会伤害自己，请立刻联系身边可信的人、当地紧急服务，或前往最近的急诊/安全地点。VibeChat 暂时不会把你送入普通聊天室。"
    if risk == SafetyRisk.violence:
        return "如果你担心自己会伤害别人，请先和对方保持距离，暂停行动，并联系可信的人或当地紧急服务。"
    if risk == SafetyRisk.severe_distress:
        return "你现在的痛苦需要被认真对待。建议先联系一个现实中的可信任的人陪伴你，或寻求当地专业支持。"
    return ""
