import json
import os
import sqlite3
from contextlib import contextmanager
from .settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY,
  format TEXT NOT NULL,
  topic TEXT NOT NULL,
  topic_tag TEXT,
  hook_type TEXT NOT NULL,
  cta_type TEXT NOT NULL,
  cards_json TEXT NOT NULL,
  body TEXT NOT NULL,
  body_hash TEXT NOT NULL UNIQUE,
  image_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  publish_attempts INTEGER NOT NULL DEFAULT 0,
  last_publish_error TEXT,
  publish_started_at TEXT,
  source_key TEXT UNIQUE,
  scheduled_at TEXT,
  slot TEXT,
  replies_json TEXT NOT NULL DEFAULT '[]',
  quality_json TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY,
  draft_id INTEGER NOT NULL,
  threads_media_id TEXT UNIQUE,
  permalink TEXT,
  published_at TEXT DEFAULT CURRENT_TIMESTAMP,
  status TEXT DEFAULT 'published',
  insight_attempts INTEGER NOT NULL DEFAULT 0,
  last_insight_attempt_at TEXT,
  last_insight_error TEXT,
  reply_ids_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY(draft_id) REFERENCES drafts(id)
);
CREATE TABLE IF NOT EXISTS metrics(
  id INTEGER PRIMARY KEY,
  post_id INTEGER NOT NULL,
  collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
  age_hours REAL DEFAULT 0,
  snapshot_label TEXT,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  reposts INTEGER DEFAULT 0,
  quotes INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  like_rate REAL DEFAULT 0,
  reply_rate REAL DEFAULT 0,
  share_rate REAL DEFAULT 0,
  weighted_score REAL DEFAULT 0,
  raw_json TEXT,
  FOREIGN KEY(post_id) REFERENCES posts(id)
);
CREATE TABLE IF NOT EXISTS knowledge(
  dimension TEXT NOT NULL,
  key TEXT NOT NULL,
  score REAL DEFAULT 1,
  samples INTEGER DEFAULT 0,
  last_result TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(dimension,key)
);
CREATE TABLE IF NOT EXISTS system_log(
  id INTEGER PRIMARY KEY,
  event TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connect():
    os.makedirs(os.path.dirname(settings.database_path) or ".", exist_ok=True)
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        columns = {row["name"] for row in con.execute("PRAGMA table_info(drafts)")}
        if "image_path" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN image_path TEXT")
        if "topic_tag" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN topic_tag TEXT")
        if "publish_attempts" not in columns:
            con.execute(
                "ALTER TABLE drafts ADD COLUMN publish_attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "last_publish_error" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN last_publish_error TEXT")
        if "publish_started_at" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN publish_started_at TEXT")
        if "source_key" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN source_key TEXT")
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_source_key "
                "ON drafts(source_key) WHERE source_key IS NOT NULL"
            )
        if "scheduled_at" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN scheduled_at TEXT")
        if "slot" not in columns:
            con.execute("ALTER TABLE drafts ADD COLUMN slot TEXT")
        if "replies_json" not in columns:
            con.execute(
                "ALTER TABLE drafts ADD COLUMN replies_json TEXT NOT NULL DEFAULT '[]'"
            )
        post_columns = {row["name"] for row in con.execute("PRAGMA table_info(posts)")}
        if "insight_attempts" not in post_columns:
            con.execute(
                "ALTER TABLE posts ADD COLUMN insight_attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "last_insight_attempt_at" not in post_columns:
            con.execute("ALTER TABLE posts ADD COLUMN last_insight_attempt_at TEXT")
        if "last_insight_error" not in post_columns:
            con.execute("ALTER TABLE posts ADD COLUMN last_insight_error TEXT")
        if "reply_ids_json" not in post_columns:
            con.execute(
                "ALTER TABLE posts ADD COLUMN reply_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        metric_columns = {row["name"] for row in con.execute("PRAGMA table_info(metrics)")}
        if "snapshot_label" not in metric_columns:
            con.execute("ALTER TABLE metrics ADD COLUMN snapshot_label TEXT")
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_metrics_post_snapshot "
            "ON metrics(post_id,snapshot_label) WHERE snapshot_label IS NOT NULL"
        )


def jdump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def log_event(event, details):
    with connect() as con:
        con.execute(
            "INSERT INTO system_log(event,details_json) VALUES(?,?)",
            (event, jdump(details)),
        )
