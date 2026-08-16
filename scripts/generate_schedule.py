import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

QUEUE_PATH = Path("data/content_queue.json")
HISTORY_PATH = Path("data/post_history.csv")
OUTPUT_PATH = Path("SCHEDULE.md")
SLOT_LABELS = {"morning": "07:00", "noon": "12:00", "evening": "20:00"}
SLOT_ORDER = {"morning": 0, "noon": 1, "evening": 2}


def load_queue():
    if not QUEUE_PATH.is_file():
        return []
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def load_published_ids():
    if not HISTORY_PATH.is_file():
        return set()
    with HISTORY_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return {row.get("kai_id", "").strip() for row in csv.DictReader(f) if row.get("kai_id")}


def main():
    queue = load_queue()
    published_ids = load_published_ids()
    now = datetime.now(ZoneInfo("Asia/Tokyo"))

    rows = []
    for item in sorted(queue, key=lambda x: (x.get("date", ""), SLOT_ORDER.get(x.get("slot"), 99))):
        post_no = item.get("post_no", "")
        if post_no in published_ids:
            state = "✅ 投稿済み"
        elif item.get("status") == "ready":
            state = "🟢 予約あり"
        elif item.get("status") in {"disabled", "cancelled"}:
            state = "⏸ 無効"
        else:
            state = f"⚪ {item.get('status', '不明')}"

        image = "🖼 あり" if item.get("image_path") else "—"
        fmt = item.get("format", "")
        rows.append(
            f"| {item.get('date','')} | {SLOT_LABELS.get(item.get('slot'), item.get('slot',''))} | "
            f"{post_no} | {fmt} | {item.get('topic','')} | {image} | {state} |"
        )

    lines = [
        "# Kai Threads 投稿スケジュール",
        "",
        "> `data/content_queue.json` と `data/post_history.csv` から自動生成します。手動編集しないでください。",
        "",
        f"最終更新: {now.strftime('%Y-%m-%d %H:%M')} JST",
        "",
        "| 日付 | 時刻 | 投稿番号 | 形式 | テーマ | 画像 | 状態 |",
        "|---|---:|---|---|---|---|---|",
        *rows,
        "",
        "## 表示",
        "",
        "- 🟢 予約あり: `status=ready` で定時投稿対象",
        "- ✅ 投稿済み: `data/post_history.csv` に公開記録あり",
        "- 🖼 あり: 親投稿に `image_path` あり",
        "- ⏸ 無効: 自動投稿対象外",
        "",
    ]
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
