import unittest

from app.analytics import _normalized_metrics, _own_reply_count
from app.cli import _with_reply_breakdown


class AnalyticsNormalizationTest(unittest.TestCase):
    def test_bot_result_replies_are_removed(self):
        values = {"views": 100, "likes": 4, "replies": 5, "reposts": 1}
        result = _normalized_metrics(values, own_reply_count=3)
        self.assertEqual(result["replies"], 2)
        self.assertEqual(result["reply_rate"], 0.02)

    def test_zero_views_stays_zero(self):
        result = _normalized_metrics({"views": 0, "likes": 2}, own_reply_count=0)
        self.assertEqual(result["views"], 0)
        self.assertEqual(result["weighted_score"], 0.0)

    def test_single_view_does_not_rank_as_perfect(self):
        result = _normalized_metrics({"views": 1, "likes": 1})
        self.assertLess(result["weighted_score"], 0.02)

    def test_only_successful_reply_ids_are_counted(self):
        self.assertEqual(_own_reply_count('["a",null,"b",""]'), 2)

    def test_export_keeps_raw_and_corrected_reply_counts(self):
        rows = _with_reply_breakdown([{
            "user_replies": 2,
            "reply_ids_json": '["a","b","c"]',
            "raw_json": '{"data":[{"name":"replies","total_value":{"value":5}}]}',
        }])
        self.assertEqual(rows[0]["replies"], 5)
        self.assertEqual(rows[0]["own_result_replies"], 3)
        self.assertEqual(rows[0]["user_replies"], 2)


if __name__ == "__main__":
    unittest.main()
