import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import connect, jdump, log_event
from .image_maker import render_post_image
from .planner import CARDS
from .safety import check
from .settings import settings


SLOTS = {"morning": "07:00", "noon": "12:00", "evening": "20:00"}
FORMATS = {
    "three_choice",
    "daily_tarot",
    "relationship_tip",
    "question",
    "event_countdown",
    "event_today",
    "empathy",
    "checklist",
    "message_example",
    "short_advice",
    "psychology",
    "poll",
    "story",
}
CARD_BY_ID = {int(card["id"]): card for card in CARDS}


def _load():
    path = Path(settings.content_queue_path)
    if not path.is_file():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("content_queue.jsonの最上位は配列である必要があります")
    return value


def _now():
    return datetime.now(ZoneInfo(settings.timezone))


def _validate(item):
    required = {"key", "date", "slot", "format", "topic", "title", "body"}
    missing = sorted(required - set(item))
    if missing:
        raise ValueError(f"予約投稿に必須項目がありません: {','.join(missing)}")
    if item["slot"] not in SLOTS:
        raise ValueError(f"不明な投稿枠です: {item['slot']}")
    if item["format"] not in FORMATS:
        raise ValueError(f"不明な投稿形式です: {item['format']}")
    quality = check(item["body"])
    if not quality["passed"]:
        raise ValueError(
            f"投稿本文が品質ゲートを通過していません: {','.join(quality['reasons'])}"
        )
    card_ids = [int(value) for value in item.get("card_ids", [])]
    if any(value not in CARD_BY_ID for value in card_ids):
        raise ValueError("存在しないカードIDが指定されています")
    if item["format"] == "three_choice":
        if len(card_ids) != 3 or len(set(card_ids)) != 3:
            raise ValueError("3択投稿には異なるカードIDが3枚必要です")
        replies = item.get("replies", [])
        if len(replies) != 3:
            raise ValueError("3択投稿にはA・B・Cの返信が3件必要です")
        if [reply.get("label") for reply in replies] != list("ABC"):
            raise ValueError("3択返信の順番はA・B・Cである必要があります")
    return quality, [CARD_BY_ID[value] for value in card_ids]


def due(slot, target_date=None):
    if slot not in SLOTS:
        raise ValueError(f"不明な投稿枠です: {slot}")
    date_text = target_date or _now().date().isoformat()
    matches = [
        item
        for item in _load()
        if item.get("date") == date_text
        and item.get("slot") == slot
        and item.get("status", "draft") == "ready"
    ]
    if len(matches) > 1:
        raise RuntimeError(f"{date_text} {slot}に複数の予約投稿があります")
    return matches[0] if matches else None


def preview(slot, target_date=None):
    item = due(slot, target_date)
    if not item:
        return {
            "status": "no_content",
            "slot": slot,
            "date": target_date or _now().date().isoformat(),
            "api_requested": False,
        }
    quality, cards = _validate(item)
    return {
        "status": "ready",
        "key": item["key"],
        "date": item["date"],
        "slot": slot,
        "format": item["format"],
        "topic": item["topic"],
        "title": item["title"],
        "body": item["body"],
        "image_path": item.get("image_path"),
        "cards": [card["name_ja"] for card in cards],
        "replies": item.get("replies", []),
        "quality": quality,
        "api_requested": False,
    }


def prepare(slot, target_date=None):
    item = due(slot, target_date)
    if not item:
        return None
    quality, cards = _validate(item)
    source_key = str(item["key"])
    with connect() as con:
        existing = con.execute(
            "SELECT * FROM drafts WHERE source_key=?", (source_key,)
        ).fetchone()
    if existing:
        existing = dict(existing)
        if existing["status"] == "published":
            return existing

        # The queue is the source of truth for content that has not been
        # published yet.  Old reset databases can contain stale image paths
        # (for example an image on a text-only post), so reconcile the draft
        # before dispatching it.
        image_path = item.get("image_path")
        if image_path:
            if not Path(image_path).is_file():
                raise FileNotFoundError(
                    f"事前生成画像がGitHub上にありません: {image_path}"
                )
            if item["format"] == "three_choice":
                for reply in item.get("replies", []):
                    reply_image = reply.get("image_path")
                    if not reply_image or not Path(reply_image).is_file():
                        raise FileNotFoundError(
                            f"3択結果画像がGitHub上にありません: {reply_image}"
                        )
        elif cards:
            current_path = existing.get("image_path")
            if current_path and Path(current_path).is_file():
                image_path = current_path
            else:
                image_path = render_post_image(
                    existing["id"],
                    item["format"],
                    item["title"],
                    cards,
                    item.get("event"),
                    item.get("image_copy"),
                )
        else:
            image_path = None

        body_hash = hashlib.sha256(item["body"].encode("utf-8")).hexdigest()
        scheduled_at = f"{item['date']}T{SLOTS[slot]}:00+09:00"
        with connect() as con:
            con.execute(
                """UPDATE drafts SET
                   format=?,topic=?,hook_type=?,cta_type=?,cards_json=?,
                   body=?,body_hash=?,quality_json=?,scheduled_at=?,slot=?,
                   replies_json=?,image_path=?
                   WHERE id=?""",
                (
                    item["format"],
                    item["topic"],
                    item["title"],
                    item.get("cta_type", "none"),
                    jdump(cards),
                    item["body"],
                    body_hash,
                    jdump(quality),
                    scheduled_at,
                    slot,
                    jdump(item.get("replies", [])),
                    image_path,
                    existing["id"],
                ),
            )
            row = con.execute(
                "SELECT * FROM drafts WHERE id=?", (existing["id"],)
            ).fetchone()
        return dict(row)

    body_hash = hashlib.sha256(item["body"].encode("utf-8")).hexdigest()
    scheduled_at = f"{item['date']}T{SLOTS[slot]}:00+09:00"
    replies = item.get("replies", [])
    with connect() as con:
        cur = con.execute(
            """INSERT INTO drafts(
               format,topic,hook_type,cta_type,cards_json,body,body_hash,
               status,quality_json,source_key,scheduled_at,slot,replies_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["format"],
                item["topic"],
                item["title"],
                item.get("cta_type", "none"),
                jdump(cards),
                item["body"],
                body_hash,
                "pending",
                jdump(quality),
                source_key,
                scheduled_at,
                slot,
                jdump(replies),
            ),
        )
        draft_id = cur.lastrowid
    image_path = item.get("image_path")
    if image_path:
        if not Path(image_path).is_file():
            raise FileNotFoundError(
                f"事前生成画像がGitHub上にありません: {image_path}"
            )
        if item["format"] == "three_choice":
            for reply in replies:
                reply_image = reply.get("image_path")
                if not reply_image or not Path(reply_image).is_file():
                    raise FileNotFoundError(
                        f"3択結果画像がGitHub上にありません: {reply_image}"
                    )
    elif cards:
        image_path = render_post_image(
            draft_id,
            item["format"],
            item["title"],
            cards,
            item.get("event"),
            item.get("image_copy"),
        )
    else:
        image_path = None
    with connect() as con:
        con.execute(
            "UPDATE drafts SET image_path=? WHERE id=?", (image_path, draft_id)
        )
        row = con.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    result = dict(row)
    log_event(
        "queued_draft_prepared",
        {
            "draft_id": draft_id,
            "source_key": source_key,
            "slot": slot,
            "scheduled_at": scheduled_at,
        },
    )
    return result
