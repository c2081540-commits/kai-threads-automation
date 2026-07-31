import json
import re
from collections import Counter
from pathlib import Path

from PIL import Image


PERIOD_START = ("2026-07-31", "evening")
PERIOD_END = ("2026-08-01", "evening")
WEEK_FOLDER = Path("generated/weeks/20260731-20260806")
SLOT_TIME = {"morning": "0700", "noon": "1200", "evening": "2000"}


def is_target(item):
    value = (item.get("date", ""), item.get("slot", ""))
    order = {"morning": 0, "noon": 1, "evening": 2}
    start = (PERIOD_START[0], order[PERIOD_START[1]])
    end = (PERIOD_END[0], order[PERIOD_END[1]])
    current = (value[0], order.get(value[1], -1))
    return start <= current <= end


def validate_schedule(queue_path="data/content_queue.json"):
    queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    posts = [item for item in queue if is_target(item) and item.get("status") == "ready"]
    errors = []
    results = []
    if len(posts) != 4:
        errors.append(f"対象期間のready投稿が4件ではありません: {len(posts)}")
    expected = [f"KAI-{index:03d}" for index in range(1, 5)]
    actual = [item.get("post_no") for item in posts]
    if actual != expected:
        errors.append(f"投稿番号または日時順が不正です: {actual}")
    paths = [item.get("image_path") for item in posts]
    duplicates = {path for path, count in Counter(paths).items() if count > 1}
    if duplicates:
        errors.append(f"親画像が複数投稿で重複しています: {sorted(duplicates)}")
    for item in posts:
        item_errors = []
        path_text = item.get("image_path", "")
        path = Path(path_text)
        expected_prefix = (
            f"{item['date'].replace('-', '')}_{SLOT_TIME[item['slot']]}_"
            f"{item['post_no']}_"
        )
        if path.parent != WEEK_FOLDER:
            item_errors.append("今回専用フォルダ以外を参照")
        if not path.name.startswith(expected_prefix):
            item_errors.append("日時・番号と画像ファイル名が不一致")
        if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", path_text):
            item_errors.append("画像パスに許可外文字")
        matches = list(path.parent.glob(path.name)) if path.name else []
        if len(matches) != 1:
            item_errors.append(f"指定親画像の存在数が1件ではない: {len(matches)}")
        elif matches[0].is_file():
            with Image.open(matches[0]) as image:
                image.load()
                expected_sizes = (
                    {(1080, 608), (1080, 1350)}
                    if item.get("format") == "three_choice"
                    else {(1080, 1350)}
                )
                if image.size not in expected_sizes:
                    item_errors.append(
                        f"親画像サイズ不正: {image.size}"
                    )
        card_ids = item.get("card_ids", [])
        replies = item.get("replies", [])
        if item["format"] == "three_choice":
            if len(card_ids) != 3 or len(set(card_ids)) != 3:
                item_errors.append("3択カードが3枚の異なるカードではない")
            if [reply.get("label") for reply in replies] != ["左", "中央", "右"]:
                item_errors.append("3択返信の順番が左・中央・右ではない")
        if item["format"] == "ab_choice":
            if len(card_ids) != 2 or len(set(card_ids)) != 2:
                item_errors.append("A/Bカードが2枚の異なるカードではない")
            if [reply.get("label") for reply in replies] != ["A", "B"]:
                item_errors.append("A/B返信の順番がA・Bではない")
        for reply in replies:
            reply_path = Path(reply.get("image_path", ""))
            if reply_path.parent != WEEK_FOLDER:
                item_errors.append(f"返信{reply.get('label')}が専用フォルダ以外を参照")
            reply_matches = list(reply_path.parent.glob(reply_path.name)) if reply_path.name else []
            if len(reply_matches) != 1:
                item_errors.append(
                    f"返信{reply.get('label')}画像の存在数が1件ではない: {len(reply_matches)}"
                )
            elif reply_matches[0].is_file():
                with Image.open(reply_matches[0]) as image:
                    image.load()
                    if image.size != (1080, 1350):
                        item_errors.append(
                            f"返信{reply.get('label')}画像サイズ不正: {image.size}"
                        )
        if item.get("image_title") != item.get("title"):
            item_errors.append("投稿本文の管理タイトルと画像タイトルが不一致")
        if not item.get("topic") or not item.get("body"):
            item_errors.append("テーマまたは投稿本文が空")
        results.append({
            "post_no": item.get("post_no"),
            "date": item.get("date"),
            "slot": item.get("slot"),
            "image_path": path_text,
            "passed": not item_errors,
            "errors": item_errors,
        })
        errors.extend(f"{item.get('post_no')}: {error}" for error in item_errors)
    return {"passed": not errors, "post_count": len(posts), "errors": errors, "results": results}


def assert_schedule(queue_path="data/content_queue.json"):
    result = validate_schedule(queue_path)
    if not result["passed"]:
        raise RuntimeError("予約データ検証失敗: " + " / ".join(result["errors"]))
    return result
