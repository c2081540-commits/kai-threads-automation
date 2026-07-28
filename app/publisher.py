import json
from urllib.parse import quote
from .db import connect, log_event
from .threads_api import ThreadsAPI
from .settings import settings


def pending():
    with connect() as con:
        return [
            dict(r) for r in con.execute(
                "SELECT * FROM drafts WHERE status='pending' ORDER BY id ASC"
            )
        ]


def publish(draft_id):
    with connect() as con:
        row = con.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("投稿可能な承認待ち案ではありません")
        if int(row["publish_attempts"] or 0) >= 1:
            raise RuntimeError("この案は既に投稿を試行済みです。自動再送を停止しました")
        quality = json.loads(row["quality_json"])
        if not quality.get("passed"):
            raise ValueError("品質ゲートを通過していません")
        if row["image_path"] and not settings.image_base_url:
            raise RuntimeError("IMAGE_BASE_URLが未設定です")
        # APIを呼ぶ前に状態を確定させる。途中失敗後の自動再送を防ぐ。
        con.execute(
            """UPDATE drafts SET status='publishing',
               publish_attempts=publish_attempts+1,
               publish_started_at=CURRENT_TIMESTAMP,last_publish_error=NULL
               WHERE id=?""",
            (draft_id,),
        )
    image_url = (
        settings.image_base_url.rstrip("/") + "/" + quote(row["image_path"])
        if row["image_path"] else None
    )
    replies = json.loads(row["replies_json"] or "[]")
    media_id = None
    permalink = None
    reply_ids = []
    try:
        api = ThreadsAPI()
        api.verify_identity()
        media_id = (
            api.publish_image(row["body"], image_url)
            if image_url else api.publish_text(row["body"])
        )
        parent_media = api.wait_until_published(media_id)
        permalink = parent_media["permalink"]
        for reply in replies:
            label = reply.get("label")
            reply_image_path = (
                reply.get("image_path")
                or (
                    f"generated/post-{draft_id:05d}-result-{label}.png"
                    if row["format"] == "three_choice" and label in "ABC"
                    else None
                )
            )
            reply_image_url = (
                settings.image_base_url.rstrip("/")
                + "/"
                + quote(reply_image_path)
                if reply_image_path
                else None
            )
            reply_id = (
                api.publish_image(reply["text"], reply_image_url, media_id)
                if reply_image_url
                else api.publish_text(reply["text"], media_id)
            )
            api.wait_until_published(reply_id)
            reply_ids.append(reply_id)
    except Exception as exc:
        with connect() as con:
            if media_id:
                con.execute(
                    """INSERT OR IGNORE INTO posts(
                       draft_id,threads_media_id,status,reply_ids_json
                       ) VALUES(?,?,?,?)""",
                    (
                        draft_id,
                        media_id,
                        "partial_reply_failure",
                        json.dumps(reply_ids, ensure_ascii=False),
                    ),
                )
                status = "partial_reply_failure"
            else:
                status = "publish_failed"
            con.execute(
                "UPDATE drafts SET status=?,last_publish_error=? WHERE id=?",
                (status, str(exc)[:1000], draft_id),
            )
        log_event(
            "post_publish_failed",
            {
                "draft_id": draft_id,
                "parent_media_id": media_id,
                "completed_reply_ids": reply_ids,
                "error": str(exc),
                "automatic_retry": False,
            },
        )
        raise

    # ID返却だけでは成功扱いにせず、公開後の取得とpermalinkを確認する。
    with connect() as con:
        cur = con.execute(
            """INSERT INTO posts(
               draft_id,threads_media_id,permalink,reply_ids_json
               ) VALUES(?,?,?,?)""",
            (
                draft_id,
                media_id,
                permalink,
                json.dumps(reply_ids, ensure_ascii=False),
            ),
        )
        con.execute("UPDATE drafts SET status='published' WHERE id=?", (draft_id,))
    result = {
        "post_id": cur.lastrowid,
        "id": media_id,
        "permalink": permalink,
        "image_url": image_url,
        "reply_ids": reply_ids,
    }
    log_event("post_published", result)
    return result
