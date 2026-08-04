import json
import re
from collections import Counter
from pathlib import Path

from PIL import Image


NEW_WEEK = Path("generated/weeks/20260805-20260811")
OLD_WEEK = Path("generated/weeks/20260731-20260806")
SLOT_TIME = {"morning": "0700", "noon": "1200", "evening": "2000"}


def validate_schedule(queue_path="data/content_queue.json"):
    queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    errors = []
    results = []
    expected = ["KAI-013"] + [f"KAI-{n:03d}" for n in range(14, 35)]
    actual = [item.get("post_no") for item in queue]
    if actual != expected:
        errors.append(f"投稿順がKAI-013〜034ではありません: {actual}")
    if len(queue) != 22:
        errors.append(f"予約件数が22件ではありません: {len(queue)}")
    if sum(1 for x in queue if x.get("post_no") == "KAI-013") != 1:
        errors.append("今夜分KAI-013が1件ではありません")
    slots = [(x.get("date"), x.get("slot")) for x in queue]
    if len(slots) != len(set(slots)):
        errors.append("同じ日時枠に複数の予約があります")

    referenced = []
    for item in queue:
        item_errors = []
        post_no = item.get("post_no", "")
        path = Path(item.get("image_path", ""))
        expected_folder = OLD_WEEK if post_no == "KAI-013" else NEW_WEEK
        if path.parent != expected_folder:
            item_errors.append("image_pathが対象generatedフォルダではありません")
        if post_no != "KAI-013":
            prefix = f"{item['date'].replace('-', '')}_{SLOT_TIME[item['slot']]}_{post_no}_"
            if not path.name.startswith(prefix):
                item_errors.append("日時・投稿番号と画像ファイル名が不一致")
            if "card_ids" in item:
                item_errors.append("新規投稿にcard_idsが混入しています")
        if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", str(path)):
            item_errors.append("image_pathに許可外文字があります")
        if not path.is_file():
            item_errors.append("親画像が存在しません")
        else:
            try:
                with Image.open(path) as image:
                    image.load()
                    expected_sizes = {(1080, 608)} if item.get("format") == "three_choice" else {(1080, 1350)}
                    if image.size not in expected_sizes:
                        item_errors.append(f"親画像サイズ不正: {image.size}")
            except Exception as exc:
                item_errors.append(f"親画像破損: {exc}")
        referenced.append(str(path))

        replies = item.get("replies", [])
        if item.get("format") == "three_choice":
            if [r.get("label") for r in replies] != ["左", "中央", "右"]:
                item_errors.append("3択返信が左・中央・右の3件ではありません")
            for reply in replies:
                rp = Path(reply.get("image_path", ""))
                if rp.parent != expected_folder:
                    item_errors.append(f"返信{reply.get('label')}のフォルダが不正です")
                if not rp.is_file():
                    item_errors.append(f"返信{reply.get('label')}画像が存在しません")
                else:
                    try:
                        with Image.open(rp) as image:
                            image.load()
                            if image.size != (1080, 1350):
                                item_errors.append(f"返信{reply.get('label')}画像サイズ不正: {image.size}")
                    except Exception as exc:
                        item_errors.append(f"返信{reply.get('label')}画像破損: {exc}")
                referenced.append(str(rp))
        elif replies:
            item_errors.append("3択以外に返信画像データがあります")

        if item.get("image_title") != item.get("title"):
            item_errors.append("titleとimage_titleが不一致です")
        if item.get("cta_type") == "comment" and not item.get("cta_word"):
            item_errors.append("コメントCTAにcta_wordがありません")
        if not item.get("body") or not item.get("topic") or not item.get("topic_tag"):
            item_errors.append("本文・テーマ・topic_tagのいずれかが空です")
        results.append({"post_no": post_no, "passed": not item_errors, "errors": item_errors})
        errors.extend(f"{post_no}: {e}" for e in item_errors)

    duplicates = [p for p, n in Counter(referenced).items() if n > 1]
    if duplicates:
        errors.append(f"同じ完成画像が複数箇所で参照されています: {duplicates}")
    actual_images = sorted(str(p) for p in Path("generated").rglob("*.png"))
    if sorted(referenced) != actual_images:
        missing = sorted(set(referenced) - set(actual_images))
        unused = sorted(set(actual_images) - set(referenced))
        errors.append(f"画像参照差分 missing={missing} unused={unused}")
    new_refs = [p for p in referenced if "20260805-20260811" in p]
    if len(new_refs) != 42:
        errors.append(f"新規参照画像が42枚ではありません: {len(new_refs)}")
    return {"passed": not errors, "post_count": len(queue), "new_image_count": len(new_refs), "errors": errors, "results": results}


def assert_schedule(queue_path="data/content_queue.json"):
    result = validate_schedule(queue_path)
    if not result["passed"]:
        raise RuntimeError("予約データ検証失敗: " + " / ".join(result["errors"]))
    return result
