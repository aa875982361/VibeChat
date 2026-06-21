from __future__ import annotations

import json
import re
from typing import Any

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import ValidationError

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
        "status_message",
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
        "status_message": {"type": "string", "minLength": 1, "maxLength": 180},
    },
}


SYSTEM_PROMPT = """
你是 VibeChat 的情绪识别器。请只分析用户当下文字中的情绪，不做诊断。
目标是帮助用户进入匿名情绪聊天室。返回 JSON 必须符合 schema。
判断 primary_emotion、复合 secondary_emotions、强度、正负倾向、唤醒度和分享意图。
如果文本表达自伤、自杀、伤害他人或极端失控风险，设置 safety_risk。
empathy_prompt 用中文，克制、温柔，不像心理咨询广告，不超过 60 个汉字。
status_message 是用户进房后可选择发送的第一人称状态描述，40-120 个中文字符。
status_message 要像用户自己说的话，不要出现“AI”“识别”“强度”“标签”“诊断”等分析口吻。
status_message 只能基于用户原文和情绪理解，不要编造用户没有说过的具体事实。
"""


async def analyze_text(text: str) -> EmotionAnalysis:
    if not settings.llm_api_key:
        return fallback_analysis(text)

    if settings.ai_provider == "anthropic":
        return await analyze_with_anthropic(text)

    client_kwargs: dict[str, str] = {"api_key": settings.llm_api_key}
    if settings.llm_base_url:
        client_kwargs["base_url"] = settings.llm_base_url
    client = AsyncOpenAI(**client_kwargs)

    if settings.ai_provider == "deepseek":
        return await analyze_with_chat_completions(client, text)

    moderation_risk = await moderate_text(client, text)
    response = await client.responses.create(
        model=settings.llm_model,
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
        analysis.empathy_prompt = empathy_for(analysis.primary_emotion, moderation_risk)
        analysis.status_message = status_message_for(text, analysis.primary_emotion, analysis.share_intent, moderation_risk)
    return analysis


async def analyze_with_chat_completions(client: AsyncOpenAI, text: str) -> EmotionAnalysis:
    local_risk = fallback_safety(text)
    json_contract = json.dumps(EMOTION_SCHEMA, ensure_ascii=False)
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n你必须返回一个 JSON object，不要使用 Markdown。字段必须完整，枚举值必须使用英文。"
                    + "\n严格遵守这个 JSON Schema 的字段、类型、范围和枚举："
                    + json_contract
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    analysis = parse_analysis_or_fallback(content, text)
    if local_risk != SafetyRisk.none:
        analysis.safety_risk = local_risk
        analysis.empathy_prompt = empathy_for(analysis.primary_emotion, local_risk)
        analysis.status_message = status_message_for(text, analysis.primary_emotion, analysis.share_intent, local_risk)
    return analysis


async def analyze_with_anthropic(text: str) -> EmotionAnalysis:
    local_risk = fallback_safety(text)
    client_kwargs: dict[str, str] = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url
    client = AsyncAnthropic(**client_kwargs)
    json_contract = json.dumps(EMOTION_SCHEMA, ensure_ascii=False)
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=900,
        temperature=0.2,
        system=(
            SYSTEM_PROMPT
            + "\n你必须只返回一个 JSON object，不要使用 Markdown，不要添加解释。"
            + "\n字段必须完整，枚举值必须使用英文。严格遵守这个 JSON Schema："
            + json_contract
        ),
        messages=[{"role": "user", "content": text}],
    )
    content = "\n".join(
        block.text for block in response.content if getattr(block, "type", "") == "text" and getattr(block, "text", "")
    )
    analysis = parse_analysis_or_fallback(content, text)
    if local_risk != SafetyRisk.none:
        analysis.safety_risk = local_risk
        analysis.empathy_prompt = empathy_for(analysis.primary_emotion, local_risk)
        analysis.status_message = status_message_for(text, analysis.primary_emotion, analysis.share_intent, local_risk)
    return analysis


def parse_analysis_or_fallback(content: str, text: str) -> EmotionAnalysis:
    try:
        return EmotionAnalysis(**json.loads(extract_json_object(content)))
    except (json.JSONDecodeError, ValidationError, ValueError):
        return fallback_analysis(text)


def extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return stripped[start : end + 1]


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
        status_message=status_message_for(text, emotion, intent, risk),
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


def status_message_for(text: str, emotion: PrimaryEmotion, intent: ShareIntent, risk: SafetyRisk) -> str:
    if risk != SafetyRisk.none:
        return "我现在的状态有点危险，可能不适合先进入普通聊天室。我需要先找一个真实的人或紧急支持陪我一下。"

    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) > 86:
        cleaned = cleaned[:86].rstrip("，。,.、 ") + "..."
    if cleaned and cleaned[-1] not in "。！？!?":
        cleaned += "。"

    endings = {
        PrimaryEmotion.joy: "这件事其实让我挺开心的，也想找个地方自然地分享一下。",
        PrimaryEmotion.gratitude: "这份被照顾到的感觉让我很想好好记住，也想和人轻轻聊聊。",
        PrimaryEmotion.sadness: "我现在有点低落，想先找个地方把这些难过慢慢说出来。",
        PrimaryEmotion.anxiety: "我现在心里有点紧，想先在这里把这口气缓一缓。",
        PrimaryEmotion.anger: "我心里有点堵，也有点不甘心，想先把这股劲说出来。",
        PrimaryEmotion.loneliness: "这种没人太懂的感觉有点重，我想先在这里被听见一下。",
        PrimaryEmotion.stress: "现在压力有点顶着，也有点累，想先找个地方喘口气。",
        PrimaryEmotion.shame: "这件事让我有点难开口，但我还是想找个地方慢慢整理一下。",
        PrimaryEmotion.confusion: "我现在还没太理清楚，只是想先把这团乱说出来一点。",
        PrimaryEmotion.neutral: "我现在没有特别强烈的情绪，只是想找个安静的地方说说话。",
    }

    if intent == ShareIntent.listen:
        endings[emotion] = "我现在更想先听听别人怎么说，也让自己慢慢靠近一点。"

    message = f"{cleaned}{endings[emotion]}"
    return message[:180]


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
