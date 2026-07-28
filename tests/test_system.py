import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

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
from app.threads_api import ThreadsAPI
from app.db import jdump
from app.queue import preview, prepare
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

            def verify_identity(self):
                return {"id": "user-1", "username": "kai"}

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

    def test_success_requires_public_permalink(self):
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

            def verify_identity(self):
                return {"id": "user-1", "username": "kai"}

            def publish_text(self, text):
                self.__class__.calls += 1
                return "media-123"

            def wait_until_published(self, media_id):
                return {
                    "id": media_id,
                    "permalink": "https://www.threads.net/@kai/post/media-123",
                }

        with patch("app.publisher.ThreadsAPI", SuccessfulAPI):
            result = publish(draft_id)

        self.assertEqual(SuccessfulAPI.calls, 1)
        self.assertEqual(result["id"], "media-123")
        self.assertEqual(
            result["permalink"],
            "https://www.threads.net/@kai/post/media-123",
        )

    def test_image_wait_requests_only_supported_container_fields(self):
        api = ThreadsAPI.__new__(ThreadsAPI)
        api.token = "test-token"
        requests = []

        def fake_get(path, params):
            requests.append((path, params))
            return {"status": "FINISHED"}

        api._get = fake_get
        api._wait_until_ready("container-123", attempts=1, interval=0)

        self.assertEqual(
            requests,
            [
                (
                    "container-123",
                    {
                        "fields": "status,error_message",
                        "access_token": "test-token",
                    },
                )
            ],
        )

    def test_publish_retries_only_media_not_found_propagation_delay(self):
        class Response:
            def __init__(self, ok, status_code, body):
                self.ok = ok
                self.status_code = status_code
                self._body = body
                self.text = __import__("json").dumps(body)

            def json(self):
                return self._body

        class Session:
            def __init__(self):
                self.calls = 0

            def post(self, url, data, timeout):
                self.calls += 1
                if self.calls < 3:
                    return Response(
                        False,
                        400,
                        {
                            "error": {
                                "code": 24,
                                "error_subcode": 4279009,
                            }
                        },
                    )
                return Response(True, 200, {"id": "published-123"})

        api = ThreadsAPI.__new__(ThreadsAPI)
        api.base = "https://graph.threads.net/v1.0"
        api.user_id = "user-1"
        api.token = "test-token"
        api.session = Session()

        with patch("time.sleep"):
            result = api._publish_container(
                "container-123", attempts=4, interval=0
            )

        self.assertEqual(result["id"], "published-123")
        self.assertEqual(api.session.calls, 3)

    def test_publish_does_not_retry_unknown_http_error(self):
        class Response:
            ok = False
            status_code = 400
            text = '{"error":{"code":10}}'

            def json(self):
                return {"error": {"code": 10}}

        class Session:
            calls = 0

            def post(self, url, data, timeout):
                self.calls += 1
                return Response()

        api = ThreadsAPI.__new__(ThreadsAPI)
        api.base = "https://graph.threads.net/v1.0"
        api.user_id = "user-1"
        api.token = "test-token"
        api.session = Session()

        with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
            api._publish_container("container-123", attempts=4, interval=0)
        self.assertEqual(api.session.calls, 1)

    def test_empty_gpt_queue_stops_without_api(self):
        Path("data").mkdir(exist_ok=True)
        Path("data/content_queue.json").write_text("[]", encoding="utf-8")
        result = preview("morning", "2030-01-01")
        self.assertEqual(result["status"], "no_content")
        self.assertFalse(result["api_requested"])

    def test_already_published_slot_fails_instead_of_green_success(self):
        from app.cli import dispatch

        with patch(
            "app.queue.preview",
            return_value={"status": "ready"},
        ), patch(
            "app.queue.prepare",
            return_value={"id": 123, "status": "published"},
        ), patch(
            "app.settings.settings",
            SimpleNamespace(auto_publish=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "再送は行っていません"):
                dispatch("morning", "2030-01-01")

    def test_three_choice_queue_keeps_answers_in_replies(self):
        Path("data").mkdir(exist_ok=True)
        queue = [
            {
                "key": "test-three-choice",
                "date": "2030-01-01",
                "slot": "evening",
                "status": "ready",
                "format": "three_choice",
                "topic": "相手の気持ち",
                "title": "今の彼の本音",
                "body": (
                    "今の彼の本音を3枚から選んでください。\n\n"
                    "一度深呼吸して、直感でA・B・Cから1枚選んでください。\n"
                    "結果は返信欄へ。"
                ),
                "card_ids": [2, 6, 18],
                "replies": [
                    {"label": "A", "text": "Aの結果です。静かに状況を見極める時期です。"},
                    {"label": "B", "text": "Bの結果です。二人の選択を整理してください。"},
                    {"label": "C", "text": "Cの結果です。不安を事実だと決めつけないでください。"},
                ],
            }
        ]
        Path("data/content_queue.json").write_text(
            __import__("json").dumps(queue, ensure_ascii=False),
            encoding="utf-8",
        )
        result = preview("evening", "2030-01-01")
        self.assertEqual(result["status"], "ready")
        self.assertNotIn("女教皇", result["body"])
        self.assertEqual([x["label"] for x in result["replies"]], list("ABC"))
        row = prepare("evening", "2030-01-01")
        self.assertTrue(os.path.isfile(row["image_path"]))

    def test_existing_text_draft_drops_stale_image_path(self):
        Path("data").mkdir(exist_ok=True)
        queue = [
            {
                "key": "test-existing-text",
                "date": "2030-01-02",
                "slot": "morning",
                "status": "ready",
                "format": "short_advice",
                "topic": "連絡",
                "title": "朝の短い助言",
                "body": "画像を使わない短文投稿では、古い画像参照を送信前に確実に削除します。",
            }
        ]
        Path("data/content_queue.json").write_text(
            __import__("json").dumps(queue, ensure_ascii=False),
            encoding="utf-8",
        )
        with connect() as con:
            con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json,source_key,scheduled_at,slot
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "short_advice",
                    "古い内容",
                    "古い題名",
                    "none",
                    "[]",
                    queue[0]["body"],
                    "old-hash",
                    "generated/post-99999.png",
                    "pending",
                    jdump({"passed": True}),
                    "test-existing-text",
                    "2030-01-02T07:00:00+09:00",
                    "morning",
                ),
            )

        row = prepare("morning", "2030-01-02")
        self.assertIsNone(row["image_path"])
        self.assertEqual(row["hook_type"], "朝の短い助言")

    def test_three_choice_publishes_abc_as_direct_parent_replies(self):
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(
                   format,topic,hook_type,cta_type,cards_json,body,body_hash,
                   image_path,status,quality_json,replies_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "three_choice",
                    "復縁",
                    "3択",
                    "コメント",
                    "[]",
                    "直感でA・B・Cから1枚選んでください。結果は返信欄へ。",
                    "direct-replies-test",
                    "generated/post-99999.png",
                    "pending",
                    jdump({"passed": True}),
                    jdump(
                        [
                            {"label": "A", "text": "Aの結果"},
                            {"label": "B", "text": "Bの結果"},
                            {"label": "C", "text": "Cの結果"},
                        ]
                    ),
                ),
            )
            draft_id = cur.lastrowid

        calls = []

        class ReplyAPI:
            def verify_identity(self):
                return {"id": "user-1", "username": "kai"}

            def publish_image(self, text, image_url, reply_to_id=None):
                calls.append((text, image_url, reply_to_id))
                return f"media-{len(calls)}"

            def publish_text(self, text, reply_to_id=None):
                raise AssertionError("画像投稿である必要があります")

            def wait_until_published(self, media_id):
                return {
                    "id": media_id,
                    "permalink": f"https://www.threads.net/@kai/post/{media_id}",
                }

        with patch("app.publisher.ThreadsAPI", ReplyAPI), patch(
            "app.publisher.settings",
            SimpleNamespace(image_base_url="https://example.com"),
        ):
            result = publish(draft_id)

        self.assertEqual(len(calls), 4)
        self.assertIsNone(calls[0][2])
        self.assertEqual(
            [call[2] for call in calls[1:]],
            ["media-1", "media-1", "media-1"],
        )
        self.assertEqual(result["reply_ids"], ["media-2", "media-3", "media-4"])


if __name__ == "__main__":
    unittest.main()
