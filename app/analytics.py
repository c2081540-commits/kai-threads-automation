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


def _own_reply_count(reply_ids_json):
    """Return only result replies that were successfully published by this bot."""
    try:
        reply_ids = json.loads(reply_ids_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return 0
    return len([reply_id for reply_id in reply_ids if reply_id])


def _normalized_metrics(values, own_reply_count=0):
    views = max(int(values.get("views", 0) or 0), 0)
    likes = max(int(values.get("likes", 0) or 0), 0)
    raw_replies = max(int(values.get("replies", 0) or 0), 0)
    replies = max(raw_replies - own_reply_count, 0)
    reposts = max(int(values.get("reposts", 0) or 0), 0)
    quotes = max(int(values.get("quotes", 0) or 0), 0)
    shares = max(int(values.get("shares", 0) or 0), 0)
    if views == 0:
        like_rate = reply_rate = share_rate = weighted = 0.0
    else:
        like_rate = likes / views
        reply_rate = replies / views
        share_rate = (reposts + quotes + shares) / views
        # Small-reach posts can show 100% rates from a single interaction.
        # Add a 50-view prior so they do not dominate the learning rankings.
        weighted = (likes + replies * 4 + (reposts + quotes + shares) * 5) / (views + 50)
    return {
        "views": views, "likes": likes, "replies": replies,
        "reposts": reposts, "quotes": quotes, "shares": shares,
        "like_rate": like_rate, "reply_rate": reply_rate,
        "share_rate": share_rate, "weighted_score": weighted,
    }


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
            v = _normalized_metrics(
                _values(raw), _own_reply_count(post["reply_ids_json"])
            )
            con.execute(
                """INSERT INTO metrics(
                   post_id,age_hours,snapshot_label,views,likes,replies,reposts,quotes,shares,
                   like_rate,reply_rate,share_rate,weighted_score,raw_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    post["id"], age, snapshot_label, v["views"],
                    v["likes"], v["replies"], v["reposts"],
                    v["quotes"], v["shares"], v["like_rate"],
                    v["reply_rate"], v["share_rate"], v["weighted_score"], jdump(raw),
                ),
            )
            # 学習値は24時間スナップショットだけで更新し、同じ投稿の重複学習を防ぐ。
            weights = {}
            if snapshot_label == "24h":
                weights = {
                    "format": _update_knowledge(con, "format", post["format"], v["weighted_score"]),
                    "topic": _update_knowledge(con, "topic", post["topic"], v["weighted_score"]),
                    "cta": _update_knowledge(con, "cta", post["cta_type"], v["weighted_score"]),
                }
            results.append({
                "post_id": post["id"], "snapshot": snapshot_label,
                "views": v["views"], "like_rate": v["like_rate"],
                "reply_rate": v["reply_rate"], "share_rate": v["share_rate"],
                "weighted_score": v["weighted_score"], "updated_weights": weights,
            })
    if errors:
        log_event("insight_fetch_failed", {"errors": errors})
    log_event(
        "analysis_completed",
        {"posts": results, "requests_used": requests_used, "errors": len(errors)},
    )
    return results


def repair_historical_metrics():
    """Recalculate stored snapshots from raw API responses using corrected rules."""
    repaired = 0
    with connect() as con:
        rows = con.execute(
            """SELECT m.id,m.raw_json,p.reply_ids_json,d.format,d.topic,d.cta_type,
                      m.snapshot_label
               FROM metrics m JOIN posts p ON p.id=m.post_id
               JOIN drafts d ON d.id=p.draft_id ORDER BY m.id"""
        ).fetchall()
        con.execute("DELETE FROM knowledge")
        for row in rows:
            raw = json.loads(row["raw_json"] or "{}")
            v = _normalized_metrics(
                _values(raw), _own_reply_count(row["reply_ids_json"])
            )
            con.execute(
                """UPDATE metrics SET views=?,likes=?,replies=?,reposts=?,quotes=?,shares=?,
                          like_rate=?,reply_rate=?,share_rate=?,weighted_score=? WHERE id=?""",
                (v["views"], v["likes"], v["replies"], v["reposts"], v["quotes"],
                 v["shares"], v["like_rate"], v["reply_rate"], v["share_rate"],
                 v["weighted_score"], row["id"]),
            )
            if row["snapshot_label"] == "24h" and v["views"] > 0:
                _update_knowledge(con, "format", row["format"], v["weighted_score"])
                _update_knowledge(con, "topic", row["topic"], v["weighted_score"])
                _update_knowledge(con, "cta", row["cta_type"], v["weighted_score"])
            repaired += 1
    return {"status": "repaired", "snapshots": repaired}
