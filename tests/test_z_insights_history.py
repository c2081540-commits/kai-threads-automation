import csv
import os
import tempfile
import unittest
from pathlib import Path

from app.analytics import _due_snapshot
from app.cli import _with_kai_id, _write_csv


class InsightsHistoryTest(unittest.TestCase):
    def test_snapshot_schedule_never_moves_backwards(self):
        self.assertIsNone(_due_snapshot(23.9, set()))
        self.assertEqual(_due_snapshot(24, set()), "24h")
        self.assertEqual(_due_snapshot(72, {"24h"}), "72h")
        self.assertEqual(_due_snapshot(168, {"24h", "72h"}), "7d")
        self.assertIsNone(_due_snapshot(200, {"7d"}))

    def test_csv_keeps_kai_id_threads_id_and_topic_tag(self):
        fields = ["kai_id", "threads_media_id", "topic_tag"]
        rows = [{
            "kai_id": "KAI-001",
            "threads_media_id": "threads-123",
            "topic_tag": "タロット占い",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "insights" / "latest.csv")
            _write_csv(path, rows, fields)
            with open(path, encoding="utf-8-sig", newline="") as handle:
                saved = list(csv.DictReader(handle))
        self.assertEqual(saved, rows)

    def test_kai_id_is_extracted_from_queue_source_key(self):
        rows = _with_kai_id([{
            "source_key": "2026-08-01-evening-kai-004",
            "threads_media_id": "threads-123",
        }])
        self.assertEqual(rows[0]["kai_id"], "KAI-004")
        self.assertNotIn("source_key", rows[0])


if __name__ == "__main__":
    unittest.main()
