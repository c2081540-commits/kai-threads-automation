import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
TEST_WORKDIR = tempfile.mkdtemp(prefix="kai-tarot-tests-")
ORIGINAL_WORKDIR = os.getcwd()
os.environ["DATABASE_PATH"] = TEST_DB
os.environ["MIN_BODY_LENGTH"] = "20"

from app.db import init_db, connect
from app.planner import plan
from app.planner import CARDS
from app.safety import check
from app.events import active_events
from app.publisher import publish
from app.db import jdump
from datetime import date


class SystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(TEST_WORKDIR)
        init_db()

    @classmethod
    def tearDownClass(cls):
        os.chdir(ORIGINAL_WORKDIR)
        if os.path.exists(TEST_DB):
            os.unlink(TEST_DB)
        shutil.rmtree(TEST_WORKDIR, ignore_errors=True)

    def test_blocks_false_guarantee(self):
        self.assertFalse(check("この方法なら必ず復縁できます。")["passed"])

    def test_allows_responsible_wording(self):
        body = "復縁できるかは二人の状況で変わります。焦る前に、別れた原因を整理しましょう。"
        self.assertTrue(check(body)["passed"])

    def test_plan_creates_non_duplicate_drafts(self):
        with connect() as con:
            before = con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
        first = plan(seed=100)
        second = plan(seed=100)
        self.assertNotEqual(first["body"], second["body"])
        with connect() as con:
            after = con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
        self.assertEqual(after - before, 2)

    def test_all_22_major_arcana_are_loaded(self):
        self.assertEqual(len(CARDS), 22)
        self.assertEqual(len({card["id"] for card in CARDS}), 22)

    def test_three_choice_uses_real_card_images(self):
        result = plan(seed=20260725)
        self.assertTrue(os.path.isfile(result["image_path"]))
        with connect() as con:
            row = con.execute(
                "SELECT cards_json FROM drafts WHERE id=?", (result["draft_id"],)
            ).fetchone()
        cards = __import__("json").loads(row["cards_json"])
        self.assertEqual(len(cards), 3)
        self.assertEqual(len({card["id"] for card in cards}), 3)

    def test_valentine_countdown_is_forced(self):
        events = active_events(date(2027, 2, 7))
        valentine = next(x for x in events if x["key"] == "valentine")
        self.assertEqual(valentine["days_left"], 7)
        self.assertTrue(valentine["forced"])

    def test_strong_event_day_is_detected(self):
        events = active_events(date(2026, 12, 24))
        christmas = next(x for x in events if x["key"] == "christmas_eve")
        self.assertEqual(christmas["days_left"], 0)

    def test_failed_publish_is_not_automatically_retried(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "one_card", "復縁", "疑問", "保存", "[]",
                    "失敗時の二重投稿防止を確認するためのテスト本文です。",
                    "publish-failure-test", None, "pending", jdump({"passed": True}),
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
        with connect() as con:
            row = con.execute(
                "SELECT status,publish_attempts FROM drafts WHERE id=?", (draft_id,)
            ).fetchone()
        self.assertEqual(row["status"], "publish_failed")
        self.assertEqual(row["publish_attempts"], 1)

    def test_success_does_not_make_extra_media_get(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "one_card", "復縁", "疑問", "保存", "[]",
                    "成功後の余計な取得をしないことを確認するテスト本文です。",
                    "publish-success-test", None, "pending", jdump({"passed": True}),
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


if __name__ == "__main__":
    unittest.main()
