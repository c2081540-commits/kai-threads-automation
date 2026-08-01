import json
from datetime import datetime, timezone
from .db import connect, jdump, log_event
from .threads_api import ThreadsAPI


SNAPSHOTS = ((168, "7d"), (72, "72h"), (24, "24h"))


def _due_snapshot(age_hours, collected):
    eligible = next(
        (label for hours, label in SNAPSHOTS if age_hours >= hours),
        None,
    )
    return eligible if eligible and eligible not in collected else None


def _values(raw):
    out = {}
    for item in raw.get("data", []):
        value = item.get("total_value", {}).get("value")
        if value is None and item.get("values"):
            value = item["values"][-1].get("value", 0)
        out[item.get("name")] = value or 0
    return out


def _age_hours(published_at):
    text = published_at.replace("Z", "+00:00")
    published = datetime.fromisoformat(text)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - published).total_seconds() / 3600


def _update_knowledge(con, dimension, key, result):
    old = con.execute(
        "SELECT score,samples FROM knowledge WHERE dimension=? AND key=?",
        (dimension, key),
    ).fetchone()
    old_score, samples = (float(old["score"]), int(old["samples"])) if old else (1.0, 0)
    target = max(0.5, min(2.0, 1.0 + result * 12))
    new_score = (old_score * samples + target) / (samples + 1)
    con.execute(
        """INSERT INTO knowledge(dimension,key,score,samples,last_result)
           VALUES(?,?,?,1,?)
           ON CONFLICT(dimension,key) DO UPDATE SET
             score=excluded.score,samples=knowledge.samples+1,
             last_result=excluded.last_result,updated_at=CURRENT_TIMESTAMP""",
        (dimension, key, new_score, f"{result:.6f}"),
    )
    return new_score


def analyze():
    api = ThreadsAPI()
    results = []
    errors = []
    max_requests_per_run = 20
    requests_used = 0
    with connect() as con:
        posts = con.execute(
            """SELECT p.*,d.format,d.topic,d.cta_type,d.hook_type
               FROM posts p JOIN drafts d ON d.id=p.draft_id
               WHERE p.status='published'
               ORDER BY p.id"""
        ).fetchall()
        for post in posts:
            if requests_used >= max_requests_per_run:
                break
            age = _age_hours(post["published_at"])
            collected = {
                row["snapshot_label"]
                for row in con.execute(
                    "SELECT snapshot_label FROM metrics WHERE post_id=?",
                    (post["id"],),
                )
                if row["snapshot_label"]
            }
            snapshot_label = _due_snapshot(age, collected)
            if not snapshot_label:
                continue
            # 取得前に回数を記録。障害時でも同一実行内で再送しない。
            con.execute(
                """UPDATE posts SET insight_attempts=insight_attempts+1,
                   last_insight_attempt_at=CURRENT_TIMESTAMP,last_insight_error=NULL
                   WHERE id=?""",
                (post["id"],),
            )
            requests_used += 1
            try:
                raw = api.insights(post["threads_media_id"])
            except Exception as exc:
                con.execute(
                    "UPDATE posts SET last_insight_error=? WHERE id=?",
                    (str(exc)[:1000], post["id"]),
                )
                errors.append({"post_id": post["id"], "error": str(exc)})
                continue
            v = _values(raw)
            views = max(int(v.get("views", 0)), 1)
            like_rate = int(v.get("likes", 0)) / views
            reply_rate = int(v.get("replies", 0)) / views
            share_count = int(v.get("reposts", 0)) + int(v.get("quotes", 0)) + int(v.get("shares", 0))
            share_rate = share_count / views
            weighted = like_rate + reply_rate * 4 + share_rate * 5
            con.execute(
                """INSERT INTO metrics(
                   post_id,age_hours,snapshot_label,views,likes,replies,reposts,quotes,shares,
                   like_rate,reply_rate,share_rate,weighted_score,raw_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    post["id"], age, snapshot_label, views,
                    v.get("likes", 0), v.get("replies", 0), v.get("reposts", 0),
                    v.get("quotes", 0), v.get("shares", 0), like_rate,
                    reply_rate, share_rate, weighted, jdump(raw),
                ),
            )
            # 学習値は24時間スナップショットだけで更新し、同じ投稿の重複学習を防ぐ。
            weights = {}
            if snapshot_label == "24h":
                weights = {
                    "format": _update_knowledge(con, "format", post["format"], weighted),
                    "topic": _update_knowledge(con, "topic", post["topic"], weighted),
                    "cta": _update_knowledge(con, "cta", post["cta_type"], weighted),
                }
            results.append({
                "post_id": post["id"], "snapshot": snapshot_label,
                "views": views, "like_rate": like_rate,
                "reply_rate": reply_rate, "share_rate": share_rate,
                "weighted_score": weighted, "updated_weights": weights,
            })
    if errors:
        log_event("insight_fetch_failed", {"errors": errors})
    log_event(
        "analysis_completed",
        {"posts": results, "requests_used": requests_used, "errors": len(errors)},
    )
    return results
