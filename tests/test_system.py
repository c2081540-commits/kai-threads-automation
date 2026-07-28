import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo


TEST_ROOT = tempfile.mkdtemp(prefix="kai-weekly-tests-")
TEST_DB = str(Path(TEST_ROOT) / "test.db")
ORIGINAL_WORKDIR = os.getcwd()
os.environ["DATABASE_PATH"] = TEST_DB
os.environ["CONTENT_QUEUE_PATH"] = str(Path(TEST_ROOT) / "data/content_queue.json")
os.environ["MIN_BODY_LENGTH"] = "20"

from app.db import connect, init_db, jdump
from app.publisher import publish
from app.queue import _validate, next_overdue
from app.safety import check
from app.weekly import load_weekly, validate_weekly


class SystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(ORIGINAL_WORKDIR)
        init_db()

    @classmethod
    def tearDownClass(cls):
        os.chdir(ORIGINAL_WORKDIR)
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_blocks_false_guarantee(self):
        self.assertFalse(check("この方法なら必ず復縁できます。")["passed"])

    def test_weekly_package_has_21_posts_and_daily_choice(self):
        result = validate_weekly(load_weekly("data/weekly_package.json"))
        self.assertEqual(result["posts"], 21)
        self.assertEqual(result["three_choice"], 7)
        self.assertGreaterEqual(len(result["formats"]), 6)

    def test_non_choice_can_be_text_only_without_cards(self):
        item = {
            "key": "text-only",
            "date": "2030-01-01",
            "slot": "morning",
            "format": "empathy",
            "topic": "不安",
            "title": "朝の不安",
            "body": "返事がない朝でも、想像だけで相手の気持ちを決めつけず、まず自分の生活を整えてください。",
            "image": {"kind": "none"},
        }
        quality, cards = _validate(item)
        self.assertTrue(quality["passed"])
        self.assertEqual(cards, [])

    def test_non_choice_rejects_meaningless_card_attachment(self):
        item = {
            "key": "bad-card",
            "date": "2030-01-01",
            "slot": "morning",
            "format": "empathy",
            "topic": "不安",
            "title": "朝の不安",
            "body": "返事がない朝でも、想像だけで相手の気持ちを決めつけず、まず自分の生活を整えてください。",
            "card_ids": [14],
            "image": {"kind": "none"},
        }
        with self.assertRaises(ValueError):
            _validate(item)

    def test_next_overdue_skips_published_and_returns_oldest_unpublished(self):
        queue_path = Path(os.environ["CONTENT_QUEUE_PATH"])
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps([
            {
                "key": "2030-01-02-morning",
                "date": "2030-01-02",
                "slot": "morning",
                "status": "ready",
            },
            {
                "key": "2030-01-02-noon",
                "date": "2030-01-02",
                "slot": "noon",
                "status": "ready",
            },
            {
                "key": "2030-01-02-evening",
                "date": "2030-01-02",
                "slot": "evening",
                "status": "ready",
            },
        ]), encoding="utf-8")
        with connect() as con:
            con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   status,quality_json,source_key
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "empathy", "復縁", "朝", "none", "[]", "朝の投稿本文",
                    "overdue-published", "published", jdump({"passed": True}),
                    "2030-01-02-morning",
                ),
            )
        now = datetime(2030, 1, 2, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertEqual(next_overdue(now)["key"], "2030-01-02-noon")

    def test_next_overdue_does_not_publish_future_slot(self):
        now = datetime(2030, 1, 1, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        with connect() as con:
            con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   status,quality_json,source_key
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "empathy", "復縁", "昼", "none", "[]", "昼の投稿本文",
                    "overdue-noon-published", "published", jdump({"passed": True}),
                    "2030-01-01-noon",
                ),
            )
        self.assertIsNone(next_overdue(now))

    def test_failed_publish_is_not_automatically_retried(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "empathy", "復縁", "疑問", "none", "[]",
                    "失敗時の二重投稿防止を確認するためのテスト本文です。",
                    "publish-failure-weekly-test", None, "pending",
                    jdump({"passed": True}),
                ),
            )
            draft_id = cur.lastrowid

        class FailingAPI:
            calls = 0

            def publish_text(self, text):
                self.__class__.calls += 1
                raise RuntimeError("simulated timeout")

        with patch("app.publisher.ThreadsAPI", FailingAPI):
            with self.assertRaises(RuntimeError):
                publish(draft_id)
            with self.assertRaises(ValueError):
                publish(draft_id)
        self.assertEqual(FailingAPI.calls, 1)

    def test_text_publish_makes_one_posting_request(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "question", "復縁", "問い", "comment", "[]",
                    "成功後の余計な取得をしないことを確認するテスト本文です。",
                    "publish-success-weekly-test", None, "pending",
                    jdump({"passed": True}),
                ),
            )
            draft_id = cur.lastrowid

        class SuccessfulAPI:
            calls = 0

            def publish_text(self, text):
                self.__class__.calls += 1
                return "media-123"

        with patch("app.publisher.ThreadsAPI", SuccessfulAPI):
            result = publish(draft_id)
        self.assertEqual(SuccessfulAPI.calls, 1)
        self.assertEqual(result["id"], "media-123")

    def test_choice_publishes_parent_then_three_replies(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json,replies_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "three_choice", "復縁", "3択", "comment", "[]",
                    "表向きのA・B・Cから直感で一枚選んでください。結果は返信欄です。",
                    "reply-chain-weekly-test", "generated/post-99999.png",
                    "pending", jdump({"passed": True}),
                    jdump([
                        {
                            "label": "A", "text": "Aの結果",
                            "image_path": "generated/post-99999-result-A.png",
                        },
                        {
                            "label": "B", "text": "Bの結果",
                            "image_path": "generated/post-99999-result-B.png",
                        },
                        {
                            "label": "C", "text": "Cの結果",
                            "image_path": "generated/post-99999-result-C.png",
                        },
                    ]),
                ),
            )
            draft_id = cur.lastrowid
        calls = []

        class ReplyAPI:
            def publish_image(self, text, image_url):
                calls.append(("image", text, image_url, None))
                return "media-parent"

            def publish_text(self, text, reply_to_id=None):
                calls.append(("text", text, None, reply_to_id))
                return f"media-reply-{len(calls) - 1}"

        with patch("app.publisher.ThreadsAPI", ReplyAPI), patch(
            "app.publisher.settings",
            SimpleNamespace(image_base_url="https://example.com"),
        ):
            result = publish(draft_id)
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0][0], "image")
        self.assertEqual([call[0] for call in calls[1:]], ["text", "text", "text"])
        self.assertEqual(
            [call[3] for call in calls[1:]],
            ["media-parent", "media-parent", "media-parent"],
        )
        self.assertEqual(
            result["reply_ids"],
            ["media-reply-1", "media-reply-2", "media-reply-3"],
        )

    def test_partial_reply_failure_resumes_without_reposting_parent(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json,replies_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "three_choice", "復縁", "3択", "comment", "[]",
                    "A・B・Cから直感で一枚選んでください。結果は返信欄です。",
                    "reply-resume-weekly-test", "generated/post-99998.png",
                    "pending", jdump({"passed": True}),
                    jdump([
                        {"label": "A", "text": "Aの結果"},
                        {"label": "B", "text": "Bの結果"},
                        {"label": "C", "text": "Cの結果"},
                    ]),
                ),
            )
            draft_id = cur.lastrowid

        first_calls = []

        class FirstAPI:
            def publish_image(self, text, image_url):
                first_calls.append(("parent", text))
                return "resume-parent"

            def publish_text(self, text, reply_to_id=None):
                first_calls.append(("reply", text, reply_to_id))
                if text == "Bの結果":
                    raise RuntimeError("simulated reply failure")
                return "resume-A"

        with patch("app.publisher.ThreadsAPI", FirstAPI), patch(
            "app.publisher.settings",
            SimpleNamespace(image_base_url="https://example.com"),
        ):
            with self.assertRaises(RuntimeError):
                publish(draft_id)

        second_calls = []

        class ResumeAPI:
            def publish_text(self, text, reply_to_id=None):
                second_calls.append((text, reply_to_id))
                return f"resume-{text[0]}"

        with patch("app.publisher.ThreadsAPI", ResumeAPI), patch(
            "app.publisher.settings",
            SimpleNamespace(image_base_url="https://example.com"),
        ):
            result = publish(draft_id)

        self.assertEqual(
            second_calls,
            [("Bの結果", "resume-parent"), ("Cの結果", "resume-parent")],
        )
        self.assertEqual(
            result["reply_ids"],
            ["resume-A", "resume-B", "resume-C"],
        )
        self.assertTrue(result["resumed"])


if __name__ == "__main__":
    unittest.main()
