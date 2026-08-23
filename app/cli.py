import argparse
import csv
import json
import os
import re
from .db import connect, init_db, log_event


def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


LATEST_PATH = "data/insights/threads_insights_latest.csv"
HISTORY_PATH = "data/insights/threads_insights_history.csv"


def _write_csv(path, rows, fallback_fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fallback_fields)
        writer.writeheader()
        writer.writerows(dict(r) for r in rows)


def _with_kai_id(rows):
    output = []
    for row in rows:
        item = dict(row)
        match = re.search(r"KAI-\d+", item.pop("source_key", "") or "", re.I)
        item["kai_id"] = match.group(0).upper() if match else ""
        output.append(item)
    return output


def _with_reply_breakdown(rows):
    output = []
    for row in rows:
        item = dict(row)
        user_replies = int(item.pop("user_replies", item.get("replies", 0)) or 0)
        try:
            reply_ids = json.loads(item.pop("reply_ids_json", "[]") or "[]")
        except (TypeError, json.JSONDecodeError):
            reply_ids = []
        own_result_replies = len([reply_id for reply_id in reply_ids if reply_id])
        try:
            raw = json.loads(item.pop("raw_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            raw = {}
        raw_replies = None
        for metric in raw.get("data", []):
            if metric.get("name") != "replies":
                continue
            raw_replies = metric.get("total_value", {}).get("value")
            if raw_replies is None and metric.get("values"):
                raw_replies = metric["values"][-1].get("value")
            break
        if raw_replies is None:
            raw_replies = user_replies + own_result_replies
        item["replies"] = max(int(raw_replies or 0), 0)
        item["own_result_replies"] = own_result_replies
        item["user_replies"] = user_replies
        output.append(item)
    return output


def export_csv(path="data/post_history.csv"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with connect() as con:
        rows = con.execute(
            """SELECT p.id,d.source_key,p.threads_media_id,p.permalink,
                      p.published_at,d.format,d.topic,d.topic_tag,d.hook_type,
                      d.cta_type,d.cards_json,d.body,m.views,m.likes,
                      m.replies AS user_replies,m.raw_json,p.reply_ids_json,m.reposts,
                      m.quotes,m.shares,m.like_rate,m.reply_rate,m.share_rate,
                      m.weighted_score,m.snapshot_label,m.age_hours,m.collected_at
               FROM posts p JOIN drafts d ON d.id=p.draft_id
               LEFT JOIN metrics m ON m.id=(
                 SELECT id FROM metrics WHERE post_id=p.id ORDER BY collected_at DESC LIMIT 1
               ) ORDER BY p.id"""
        ).fetchall()
        history = con.execute(
            """SELECT m.collected_at,d.source_key,p.threads_media_id,
                      p.permalink,p.published_at,d.format,d.topic,d.topic_tag,
                      m.snapshot_label,m.age_hours,m.views,m.likes,
                      m.replies AS user_replies,m.raw_json,p.reply_ids_json,
                      m.reposts,m.quotes,m.shares,m.like_rate,m.reply_rate,
                      m.share_rate,m.weighted_score
               FROM metrics m JOIN posts p ON p.id=m.post_id
               JOIN drafts d ON d.id=p.draft_id
               ORDER BY m.collected_at,p.id"""
        ).fetchall()
    rows = _with_reply_breakdown(_with_kai_id(rows))
    history = _with_reply_breakdown(_with_kai_id(history))
    fields = [
        "id","kai_id","threads_media_id","permalink","published_at","format",
        "topic","topic_tag","hook_type","cta_type",
        "cards_json","body","views","likes","replies","own_result_replies","user_replies",
        "reposts","quotes","shares","like_rate",
        "reply_rate","share_rate","weighted_score","snapshot_label","age_hours","collected_at",
    ]
    _write_csv(path, rows, fields)
    _write_csv(LATEST_PATH, rows, fields)
    history_fields = [
        "collected_at","kai_id","threads_media_id","permalink","published_at",
        "format","topic","topic_tag","snapshot_label","age_hours","views","likes",
        "replies","own_result_replies","user_replies","reposts","quotes","shares",
        "like_rate","reply_rate","share_rate",
        "weighted_score",
    ]
    _write_csv(HISTORY_PATH, history, history_fields)
    report_path = "data/analysis_report.md"
    with connect() as con:
        knowledge = con.execute(
            "SELECT dimension,key,score,samples,last_result FROM knowledge ORDER BY dimension,score DESC"
        ).fetchall()
        best_posts = con.execute(
            """SELECT p.permalink,d.format,d.topic,d.cta_type,m.views,m.likes,m.replies,
                      m.reposts,m.quotes,m.shares,m.weighted_score
               FROM metrics m JOIN posts p ON p.id=m.post_id
               JOIN drafts d ON d.id=p.draft_id
               WHERE m.snapshot_label='24h' AND m.views>0
               ORDER BY m.weighted_score DESC LIMIT 10"""
        ).fetchall()
    lines = [
        "# Threads自動分析レポート",
        "",
        "投稿後24時間・72時間・7日の反応推移を記録し、24時間値を次回の投稿選定へ反映します。",
        "返信評価は、API生返信数から実際に公開成功した自動結果返信ID数を除いたユーザー返信数を使用します。",
        "",
        "## 学習した投稿パターン",
        "",
        "|分類|項目|重み|評価回数|直近評価|",
        "|---|---|---:|---:|---:|",
    ]
    if knowledge:
        for row in knowledge:
            lines.append(
                f"|{row['dimension']}|{row['key']}|{row['score']:.3f}|"
                f"{row['samples']}|{row['last_result'] or '-'}|"
            )
    else:
        lines.append("|—|データ蓄積前|—|0|—|")
    lines.extend([
        "",
        "## 成績上位の投稿",
        "",
        "|形式|テーマ|CTA|表示|いいね|ユーザー返信|シェア系|評価値|",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    if best_posts:
        for row in best_posts:
            share_total = row["reposts"] + row["quotes"] + row["shares"]
            lines.append(
                f"|{row['format']}|{row['topic']}|{row['cta_type']}|{row['views']}|"
                f"{row['likes']}|{row['replies']}|{share_total}|{row['weighted_score']:.4f}|"
            )
    else:
        lines.append("|—|データ蓄積前|—|0|0|0|0|—|")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return {
        "path": path, "latest_path": LATEST_PATH, "history_path": HISTORY_PATH,
        "report_path": report_path, "rows": len(rows), "history_rows": len(history),
    }


def cycle():
    from .analytics import analyze
    from .planner import plan
    from .publisher import publish
    from .settings import settings
    analysis = []
    if (
        settings.auto_analyze
        and settings.threads_user_id
        and settings.threads_access_token
    ):
        analysis = analyze()
    draft = plan()
    exported = export_csv()
    result = {"analysis": analysis, "draft": draft, "published": None, "export": exported}
    log_event("cycle_completed", result)
    return result


def verify_auth():
    from .threads_api import ThreadsAPI

    identity = ThreadsAPI().verify_identity()
    return {
        "status": "ok",
        "username": identity["username"],
        "user_id_matches": True,
        "api_requests": 1,
        "posting_requests": 0,
    }


def preview_slot(slot, target_date=None):
    from .queue import preview

    return preview(slot, target_date)


def prepare_slot(slot, target_date=None):
    from .queue import prepare

    row = prepare(slot, target_date)
    if not row:
        return {
            "status": "no_content",
            "slot": slot,
            "date": target_date,
            "api_requested": False,
        }
    return {
        "status": "prepared",
        "draft_id": row["id"],
        "source_key": row["source_key"],
        "slot": row["slot"],
        "scheduled_at": row["scheduled_at"],
        "image_path": row["image_path"],
        "api_requested": False,
        "posting_requests": 0,
    }


def dispatch(slot, target_date=None):
    from .publisher import publish
    from .queue import prepare, preview
    from .settings import settings

    safe_preview = preview(slot, target_date)
    if safe_preview["status"] == "no_content":
        return safe_preview
    if not settings.auto_publish:
        return {
            **safe_preview,
            "status": "preview_only",
            "reason": "AUTO_PUBLISHがtrueではないため投稿しませんでした",
        }
    row = prepare(slot, target_date)
    if not row:
        return {
            "status": "no_content",
            "slot": slot,
            "api_requested": False,
        }
    if row["status"] == "published":
        raise RuntimeError(
            "この投稿枠は既に公開済みとして記録されています。"
            "Threads APIへの再送は行っていません。"
        )
    if row["status"] != "pending":
        raise RuntimeError(
            f"予約投稿は再送できない状態です: {row['status']}"
        )
    return {"status": "published", **publish(row["id"])}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--seed", type=int)
    sub.add_parser("pending")
    sub.add_parser("analyze")
    sub.add_parser("repair-insights")
    sub.add_parser("cycle")
    sub.add_parser("export")
    sub.add_parser("publish-latest")
    sub.add_parser("verify-auth")
    preview_cmd = sub.add_parser("preview-slot")
    preview_cmd.add_argument("slot", choices=("morning", "noon", "evening"))
    preview_cmd.add_argument("--date")
    prepare_cmd = sub.add_parser("prepare-slot")
    prepare_cmd.add_argument("slot", choices=("morning", "noon", "evening"))
    prepare_cmd.add_argument("--date")
    dispatch_cmd = sub.add_parser("dispatch")
    dispatch_cmd.add_argument("slot", choices=("morning", "noon", "evening"))
    dispatch_cmd.add_argument("--date")
    publish_cmd = sub.add_parser("publish")
    publish_cmd.add_argument("draft_id", type=int)
    args = parser.parse_args()

    init_db()
    if args.cmd == "init":
        show({"status": "initialized"})
    elif args.cmd == "plan":
        from .planner import plan
        show(plan(args.seed))
    elif args.cmd == "repair-insights":
        from .analytics import repair_historical_metrics
        show(repair_historical_metrics())
    elif args.cmd == "pending":
        from .publisher import pending
        show(pending())
    elif args.cmd == "publish":
        from .publisher import publish
        show(publish(args.draft_id))
    elif args.cmd == "publish-latest":
        from .publisher import pending, publish
        rows = pending()
        if not rows:
            raise RuntimeError("投稿待ちの案がありません")
        show(publish(rows[0]["id"]))
    elif args.cmd == "verify-auth":
        show(verify_auth())
    elif args.cmd == "preview-slot":
        show(preview_slot(args.slot, args.date))
    elif args.cmd == "prepare-slot":
        show(prepare_slot(args.slot, args.date))
    elif args.cmd == "dispatch":
        show(dispatch(args.slot, args.date))
    elif args.cmd == "analyze":
        from .analytics import analyze
        show(analyze())
    elif args.cmd == "cycle":
        show(cycle())
    elif args.cmd == "export":
        show(export_csv())


if __name__ == "__main__":
    main()
