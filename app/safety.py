import re
from .settings import settings

BLOCKED = [
    r"必ず復縁",
    r"絶対に復縁",
    r"確実に連絡",
    r"\d+時間以内に連絡",
    r"いいね(?:すれば|すると).*(?:叶う|復縁|連絡)",
    r"スキップすると",
    r"二度と(?:ありません|来ません)",
    r"波動を受け取",
    r"呪い",
]


def check(body: str) -> dict:
    reasons = []
    if len(body) < settings.min_body_length:
        reasons.append("本文が短すぎます")
    if len(body) > settings.max_body_length:
        reasons.append("本文が500文字を超えています")
    for pattern in BLOCKED:
        if re.search(pattern, body):
            reasons.append(f"誤認・煽り表現:{pattern}")
    if not any(mark in body for mark in ("？", "。", "A", "①")):
        reasons.append("投稿としての構造が不足しています")
    return {"passed": not reasons, "reasons": reasons, "length": len(body)}
