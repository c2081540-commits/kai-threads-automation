import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from .queue import FORMATS, SLOTS, _validate, prepare
from .settings import settings


WEEKLY_PATH = Path("data/weekly_package.json")
SLOT_ORDER = {"morning": 0, "noon": 1, "evening": 2}


def load_weekly(path=WEEKLY_PATH):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("posts"), list):
        raise ValueError("weekly_package.jsonはposts配列を持つオブジェクトにしてください")
    return value


def validate_weekly(package):
    posts = package["posts"]
    if len(posts) != 21:
        raise ValueError(f"週次パッケージは21投稿必要です（現在{len(posts)}件）")
    start = date.fromisoformat(package["week_start"])
    expected_dates = {(start + timedelta(days=i)).isoformat() for i in range(7)}
    dates = Counter(item.get("date") for item in posts)
    if set(dates) != expected_dates or any(value != 3 for value in dates.values()):
        raise ValueError("7日間それぞれに3投稿ずつ必要です")
    for day in expected_dates:
        slots = {item.get("slot") for item in posts if item.get("date") == day}
        if slots != set(SLOTS):
            raise ValueError(f"{day}にmorning/noon/eveningが1件ずつ必要です")
        choices = [
            item for item in posts
            if item.get("date") == day and item.get("format") == "three_choice"
        ]
        if len(choices) != 1:
            raise ValueError(f"{day}の3択投稿はちょうど1件必要です")
    keys = [str(item.get("key", "")) for item in posts]
    if len(set(keys)) != len(keys) or any(not key for key in keys):
        raise ValueError("投稿keyは空欄不可・重複不可です")
    titles = [item.get("title", "").strip() for item in posts]
    bodies = [item.get("body", "").strip() for item in posts]
    if len(set(titles)) != len(titles) or len(set(bodies)) != len(bodies):
        raise ValueError("タイトルまたは本文が完全重複しています")
    for index, left in enumerate(bodies):
        for right in bodies[index + 1:]:
            if SequenceMatcher(None, left, right).ratio() >= 0.84:
                raise ValueError("本文が酷似する投稿があります")
    for item in posts:
        _validate(item)
    if sum(item["format"] == "three_choice" for item in posts) != 7:
        raise ValueError("3択投稿は週7件必要です")
    if len({item["format"] for item in posts}) < 6:
        raise ValueError("AI的な単調さを避けるため、週6形式以上を使用してください")
    return {
        "status": "valid",
        "week_start": package["week_start"],
        "posts": 21,
        "three_choice": 7,
        "formats": dict(Counter(item["format"] for item in posts)),
        "api_requested": False,
        "posting_requests": 0,
    }


def install_queue(package, queue_path=None):
    validate_weekly(package)
    path = Path(queue_path or settings.content_queue_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(package["posts"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _schedule_report(package):
    posts = sorted(
        package["posts"],
        key=lambda item: (item["date"], SLOT_ORDER[item["slot"]]),
    )
    lines = [
        f"# 投稿予約一覧｜{package['week_start']}週",
        "",
        f"- 作成日時: {package.get('generated_at', '-')}",
        "- 投稿時間: 07:00 / 12:00 / 20:00（日本時間）",
        "- 3択占い: 1日1回",
        "",
        "|日付|時刻|形式|テーマ|タイトル|画像|状態|",
        "|---|---:|---|---|---|---|---|",
    ]
    for item in posts:
        image = item.get("image", {}).get("kind", "none")
        lines.append(
            f"|{item['date']}|{SLOTS[item['slot']]}|{item['format']}|"
            f"{item['topic']}|{item['title']}|{image}|{item.get('status', 'draft')}|"
        )
    lines.extend(["", "## 原稿全文", ""])
    for item in posts:
        lines.extend([
            f"### {item['date']} {SLOTS[item['slot']]}｜{item['title']}",
            "",
            item["body"],
            "",
        ])
        if item.get("replies"):
            for reply in item["replies"]:
                lines.extend([f"**返信{reply['label']}**", "", reply["text"], ""])
    return "\n".join(lines) + "\n"


def _analysis_report(package):
    analysis = package.get("analysis", {})
    experiment = package.get("experiment", {})
    lines = [
        f"# 週次分析レポート｜{package['week_start']}週",
        "",
        "## 前週の要約",
        "",
        analysis.get("summary", "初回運用のため比較データはありません。"),
        "",
        "## 成功パターン",
        "",
    ]
    successes = analysis.get("success_patterns", [])
    lines.extend([f"- {x}" for x in successes] or ["- データ蓄積前"])
    lines.extend(["", "## 改善対象（最大3項目）", ""])
    improvements = analysis.get("improvements", [])
    lines.extend([f"- {x}" for x in improvements[:3]] or ["- 初週は基準値を収集"])
    lines.extend([
        "",
        "## 今週の実験",
        "",
        f"- ID: {experiment.get('id', 'EXP-001')}",
        f"- 変更: {experiment.get('change', '投稿形式を分散する')}",
        f"- 目的: {experiment.get('goal', '反応の基準値を作る')}",
        f"- 成功条件: {experiment.get('success_condition', '前週比較は次週から判定')}",
        "",
        "## システム状態",
        "",
        "- 原稿生成: ChatGPTで週1回",
        "- 投稿処理: GitHub Actions",
        "- OpenAI API: 未使用",
        "- 自動再送: なし",
    ])
    return "\n".join(lines) + "\n"


def prepare_week(path=WEEKLY_PATH):
    package = load_weekly(path)
    validation = validate_weekly(package)
    install_queue(package)
    results = []
    for item in sorted(
        package["posts"],
        key=lambda row: (row["date"], SLOT_ORDER[row["slot"]]),
    ):
        row = prepare(item["slot"], item["date"])
        results.append({
            "key": item["key"],
            "draft_id": row["id"],
            "image_path": row["image_path"],
        })
    latest = Path("reports/latest")
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "schedule.md").write_text(_schedule_report(package), encoding="utf-8")
    (latest / "analysis.md").write_text(_analysis_report(package), encoding="utf-8")
    archive = Path("reports") / datetime.fromisoformat(
        package["week_start"]
    ).strftime("%G-W%V")
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "schedule.md").write_text(_schedule_report(package), encoding="utf-8")
    (archive / "analysis.md").write_text(_analysis_report(package), encoding="utf-8")
    return {
        **validation,
        "status": "prepared",
        "prepared": len(results),
        "images": sum(bool(item["image_path"]) for item in results),
        "reports": [
            "reports/latest/schedule.md",
            "reports/latest/analysis.md",
        ],
        "api_requested": False,
        "posting_requests": 0,
    }
