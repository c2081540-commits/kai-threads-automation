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
        quality = json.loads(row["quality_json"])
        if not quality.get("passed"):
            raise ValueError("品質ゲートを通過していません")
    api = ThreadsAPI()
    image_url = None
    if row["image_path"]:
        if not settings.image_base_url:
            raise RuntimeError("IMAGE_BASE_URLが未設定です")
        image_url = settings.image_base_url.rstrip("/") + "/" + quote(row["image_path"])
        media_id = api.publish_image(row["body"], image_url)
    else:
        media_id = api.publish_text(row["body"])
    media = api.media(media_id)
    with connect() as con:
        cur = con.execute(
            "INSERT INTO posts(draft_id,threads_media_id,permalink,published_at) VALUES(?,?,?,COALESCE(?,CURRENT_TIMESTAMP))",
            (draft_id, media_id, media.get("permalink"), media.get("timestamp")),
        )
        con.execute("UPDATE drafts SET status='published' WHERE id=?", (draft_id,))
    result = {"post_id": cur.lastrowid, "image_url": image_url, **media}
    log_event("post_published", result)
    return result
