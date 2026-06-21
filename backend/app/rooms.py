from __future__ import annotations

from .schemas import EmotionAnalysis, PrimaryEmotion, RoomOut


ROOM_COPY = {
    PrimaryEmotion.joy: ("快乐回音室", "把开心放在这里，不必解释，也不用担心被误解。"),
    PrimaryEmotion.gratitude: ("暖光分享室", "适合分享被照亮的瞬间，让快乐自然落地。"),
    PrimaryEmotion.sadness: ("低潮陪伴室", "这里先不急着解决问题，只把难过好好接住。"),
    PrimaryEmotion.anxiety: ("焦虑缓冲室", "给紧绷的心一点空间，和同频的人慢慢说。"),
    PrimaryEmotion.anger: ("情绪降温室", "允许生气被看见，也给表达留一点边界。"),
    PrimaryEmotion.loneliness: ("孤独同频室", "不用假装热闹，先和相似的安静待一会。"),
    PrimaryEmotion.stress: ("压力卸载室", "把撑太久的部分放下来，听见彼此的疲惫。"),
    PrimaryEmotion.shame: ("柔软角落", "适合说出那些不想被熟人看见的难堪。"),
    PrimaryEmotion.confusion: ("混乱整理室", "当情绪还没成形，先一起把线头找出来。"),
    PrimaryEmotion.neutral: ("日常呼吸室", "没有强烈情绪也可以说话，保持轻轻的连接。"),
}


def intensity_bucket(intensity: int) -> str:
    if intensity <= 2:
        return "low"
    if intensity == 3:
        return "medium"
    return "high"


def bucket_label(bucket: str) -> str:
    return {"low": "轻柔", "medium": "同频", "high": "深水"}.get(bucket, "同频")


def room_for_analysis(analysis: EmotionAnalysis) -> RoomOut:
    bucket = intensity_bucket(analysis.intensity)
    base_name, description = ROOM_COPY[analysis.primary_emotion]
    return RoomOut(
        id=f"{analysis.primary_emotion.value}-{bucket}",
        primary_emotion=analysis.primary_emotion,
        intensity_bucket=bucket,
        name=f"{bucket_label(bucket)}{base_name}",
        description=description,
        online_count=0,
    )

