import json
from datetime import date, datetime
from pathlib import Path

INBOX = Path("data/research_inbox.json")


def load_research(today: date | None = None) -> list[dict]:
    today = today or date.today()
    if not INBOX.exists():
        return []
    try:
        payload = json.loads(INBOX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = payload.get("candidates", payload if isinstance(payload, list) else [])
    valid = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        expires = row.get("expires_at")
        if expires:
            try:
                if date.fromisoformat(expires[:10]) < today:
                    continue
            except ValueError:
                continue
        discovered = row.get("discovered_at", today.isoformat())
        try:
            age = max((today - date.fromisoformat(discovered[:10])).days, 0)
        except ValueError:
            age = 30
        urgency = max(0, min(int(row.get("urgency", 5)), 10))
        demand = max(0, min(int(row.get("demand", 5)), 10))
        comment = max(0, min(int(row.get("comment_potential", 5)), 10))
        row = dict(row)
        row["market_score"] = urgency * 2 + demand * 1.5 + comment - age * 0.5
        row["source_type"] = "market"
        valid.append(row)
    return sorted(valid, key=lambda x: x["market_score"], reverse=True)


def write_empty_inbox():
    if INBOX.exists():
        return
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    INBOX.write_text(
        json.dumps(
            {
                "generated_at": None,
                "candidates": [],
                "schema": {
                    "title": "投稿テーマ",
                    "topic": "相手の気持ち|音信不通|冷却期間|復縁行動",
                    "angle": "投稿の切り口",
                    "why_now": "今扱う理由",
                    "suggested_format": "three_choice|one_card|checklist|question",
                    "urgency": "0-10",
                    "demand": "0-10",
                    "comment_potential": "0-10",
                    "discovered_at": "YYYY-MM-DD",
                    "expires_at": "YYYY-MM-DD",
                    "source_urls": [],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
