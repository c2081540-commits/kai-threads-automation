import os
import tempfile
import unittest

TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_PATH"] = TEST_DB
os.environ["MIN_BODY_LENGTH"] = "20"

from app.db import init_db, connect
from app.planner import plan
from app.safety import check
from app.events import active_events
from datetime import date


class SystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB):
            os.unlink(TEST_DB)

    def test_blocks_false_guarantee(self):
        self.assertFalse(check("この方法なら必ず復縁できます。")["passed"])

    def test_allows_responsible_wording(self):
        body = "復縁できるかは二人の状況で変わります。焦る前に、別れた原因を整理しましょう。"
        self.assertTrue(check(body)["passed"])

    def test_plan_creates_non_duplicate_drafts(self):
        first = plan(seed=100)
        second = plan(seed=100)
        self.assertNotEqual(first["body"], second["body"])
        with connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 2)

    def test_valentine_countdown_is_forced(self):
        events = active_events(date(2027, 2, 7))
        valentine = next(x for x in events if x["key"] == "valentine")
        self.assertEqual(valentine["days_left"], 7)
        self.assertTrue(valentine["forced"])

    def test_strong_event_day_is_detected(self):
        events = active_events(date(2026, 12, 24))
        christmas = next(x for x in events if x["key"] == "christmas_eve")
        self.assertEqual(christmas["days_left"], 0)


if __name__ == "__main__":
    unittest.main()
