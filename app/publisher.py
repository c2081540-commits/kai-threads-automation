import json
from urllib.parse import quote

from .db import connect, jdump, log_event
from .settings import settings
from .threads_api import ThreadsAPI


RESUMABLE = {"pending", "partial_reply_failure"}


def pending():
    with connect() as con:
        return [
            dict(row)
            for row in con.execute(
                "SELECT * FROM drafts WHERE status IN ('pending','partial_reply_failure') "
                "ORDER BY id ASC"
            )
        ]


def _load_state(draft_id):
    with connect() as con:
        row = con.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        post = con.execute(
            "SELECT * FROM posts WHERE draft_id=? ORDER BY id DESC LIMIT 1",
            (draft_id,),
        ).fetchone()
    return row, post


def _validate(row, post):
    if not row or row["status"] not in RESUMABLE:
        raise ValueError("投稿または返信再開が可能な案ではありません")
    quality = json.loads(row["quality_json"])
    if not quality.get("passed"):
        raise ValueError("品質ゲートを通過していません")
    if row["status"] == "pending":
        if int(row["publish_attempts"] or 0) >= 1:
            raise RuntimeError("親投稿は既に試行済みです。自動再送を停止しました")
        if row["image_path"] and not settings.image_base_url:
            raise RuntimeError("IMAGE_BASE_URLが未設定です")
    if row["status"] == "partial_reply_failure" and not post:
        raise RuntimeError("親投稿IDが保存されていないため返信を再開できません")


def _store_parent(draft_id, parent_id):
    with connect() as con:
        cur = con.execute(
            """INSERT OR IGNORE INTO posts(
               draft_id,threads_media_id,status,reply_ids_json
               ) VALUES(?,?,?,?)""",
            (draft_id, parent_id, "publishing_replies", "[]"),
        )
        post = con.execute(
            "SELECT * FROM posts WHERE draft_id=? ORDER BY id DESC LIMIT 1",
            (draft_id,),
        ).fetchone()
        con.execute(
            "UPDATE drafts SET status='publishing_replies' WHERE id=?",
            (draft_id,),
        )
    return cur.lastrowid or post["id"]


def _store_reply(draft_id, reply_ids):
    with connect() as con:
        con.execute(
            """UPDATE posts SET reply_ids_json=?,status='publishing_replies'
               WHERE id=(SELECT id FROM posts WHERE draft_id=?
                         ORDER BY id DESC LIMIT 1)""",
            (jdump(reply_ids), draft_id),
        )


def _store_failure(draft_id, parent_id, reply_ids, exc):
    status = "partial_reply_failure" if parent_id else "publish_failed"
    with connect() as con:
        if parent_id:
            con.execute(
                """UPDATE posts SET status=?,reply_ids_json=?
                   WHERE id=(SELECT id FROM posts WHERE draft_id=?
                             ORDER BY id DESC LIMIT 1)""",
                (status, jdump(reply_ids), draft_id),
            )
        con.execute(
            "UPDATE drafts SET status=?,last_publish_error=? WHERE id=?",
            (status, str(exc)[:4000], draft_id),
        )
    log_event(
        "post_publish_failed",
        {
            "draft_id": draft_id,
            "parent_media_id": parent_id,
            "completed_reply_ids": reply_ids,
            "error": str(exc),
            "automatic_retry": False,
        },
    )


def publish(draft_id):
    row, post = _load_state(draft_id)
    _validate(row, post)
    replies = json.loads(row["replies_json"] or "[]")
    parent_id = str(post["threads_media_id"]) if post else None
    reply_ids = json.loads(post["reply_ids_json"] or "[]") if post else []

    if row["status"] == "pending":
        with connect() as con:
            con.execute(
                """UPDATE drafts SET status='publishing',
                   publish_attempts=publish_attempts+1,
                   publish_started_at=CURRENT_TIMESTAMP,last_publish_error=NULL
                   WHERE id=?""",
                (draft_id,),
            )

    image_url = (
        settings.image_base_url.rstrip("/") + "/" + quote(row["image_path"])
        if row["image_path"]
        else None
    )

    try:
        api = ThreadsAPI()
        if not parent_id:
            parent_id = (
                api.publish_image(row["body"], image_url)
                if image_url
                else api.publish_text(row["body"])
            )
            _store_parent(draft_id, parent_id)

        for reply in replies[len(reply_ids):]:
            reply_id = api.publish_text(reply["text"], reply_to_id=parent_id)
            reply_ids.append(reply_id)
            _store_reply(draft_id, reply_ids)
    except Exception as exc:
        _store_failure(draft_id, parent_id, reply_ids, exc)
        raise

    with connect() as con:
        post_row = con.execute(
            "SELECT id FROM posts WHERE draft_id=? ORDER BY id DESC LIMIT 1",
            (draft_id,),
        ).fetchone()
        con.execute(
            "UPDATE posts SET status='published',reply_ids_json=? WHERE id=?",
            (jdump(reply_ids), post_row["id"]),
        )
        con.execute(
            "UPDATE drafts SET status='published',last_publish_error=NULL WHERE id=?",
            (draft_id,),
        )
    result = {
        "post_id": post_row["id"],
        "id": parent_id,
        "image_url": image_url,
        "reply_ids": reply_ids,
        "resumed": bool(post),
    }
    log_event("post_published", result)
    return result
