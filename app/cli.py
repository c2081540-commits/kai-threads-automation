import argparse
import csv
import json
import os
from .db import connect, init_db, log_event


def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def export_csv(path="data/post_history.csv"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with connect() as con:
        rows = con.execute(
            """SELECT p.id,p.permalink,p.published_at,d.format,d.topic,d.hook_type,
                      d.cta_type,d.body,m.views,m.likes,m.replies,m.reposts,
                      m.quotes,m.shares,m.like_rate,m.reply_rate,m.share_rate,
                      m.weighted_score,m.collected_at
               FROM posts p JOIN drafts d ON d.id=p.draft_id
               LEFT JOIN metrics m ON m.id=(
                 SELECT id FROM metrics WHERE post_id=p.id ORDER BY collected_at DESC LIMIT 1
               ) ORDER BY p.id"""
        ).fetchall()
    fields = list(rows[0].keys()) if rows else [
        "id","permalink","published_at","format","topic","hook_type","cta_type",
        "body","views","likes","replies","reposts","quotes","shares","like_rate",
        "reply_rate","share_rate","weighted_score","collected_at",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(r) for r in rows)
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
               ORDER BY m.weighted_score DESC LIMIT 10"""
        ).fetchall()
    lines = [
        "# Threads自動分析レポート",
        "",
        "投稿後18時間以上経過した時点の反応を使い、次回の投稿選定へ反映します。",
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
        "|形式|テーマ|CTA|表示|いいね|返信|シェア系|評価値|",
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
    return {"path": path, "report_path": report_path, "rows": len(rows)}


def cycle():
    from .analytics import analyze
    from .planner import plan
    from .publisher import publish
    from .settings import settings
    analysis = []
    if settings.threads_user_id and settings.threads_access_token:
        analysis = analyze()
    draft = plan()
    exported = export_csv()
    result = {"analysis": analysis, "draft": draft, "published": None, "export": exported}
    log_event("cycle_completed", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--seed", type=int)
    sub.add_parser("pending")
    sub.add_parser("analyze")
    sub.add_parser("cycle")
    sub.add_parser("export")
    sub.add_parser("publish-latest")
    publish_cmd = sub.add_parser("publish")
    publish_cmd.add_argument("draft_id", type=int)
    args = parser.parse_args()

    init_db()
    if args.cmd == "init":
        show({"status": "initialized"})
    elif args.cmd == "plan":
        from .planner import plan
        show(plan(args.seed))
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
    elif args.cmd == "analyze":
        from .analytics import analyze
        show(analyze())
    elif args.cmd == "cycle":
        show(cycle())
    elif args.cmd == "export":
        show(export_csv())


if __name__ == "__main__":
    main()
