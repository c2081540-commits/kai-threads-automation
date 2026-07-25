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
    try:
        api = ThreadsAPI()
        media_id = (
            api.publish_image(row["body"], image_url)
            if image_url else api.publish_text(row["body"])
        )
    except Exception as exc:
        with connect() as con:
            con.execute(
                "UPDATE drafts SET status='publish_failed',last_publish_error=? WHERE id=?",
                (str(exc)[:1000], draft_id),
            )
        log_event("post_publish_failed", {"draft_id": draft_id, "error": str(exc)})
        raise

    # threads_publish がIDを返した時点で成功扱いにする。
    # permalink取得のための追加GETは行わず、不要なAPI要求と二重投稿を防ぐ。
    with connect() as con:
        cur = con.execute(
            "INSERT INTO posts(draft_id,threads_media_id) VALUES(?,?)",
            (draft_id, media_id),
        )
        con.execute("UPDATE drafts SET status='published' WHERE id=?", (draft_id,))
    result = {
        "post_id": cur.lastrowid,
        "id": media_id,
        "image_url": image_url,
    }
    log_event("post_published", result)
    return result
