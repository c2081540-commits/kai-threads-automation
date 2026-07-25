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
  hook_type TEXT NOT NULL,
  cta_type TEXT NOT NULL,
  cards_json TEXT NOT NULL,
  body TEXT NOT NULL,
  body_hash TEXT NOT NULL UNIQUE,
  image_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
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
  FOREIGN KEY(draft_id) REFERENCES drafts(id)
);
CREATE TABLE IF NOT EXISTS metrics(
  id INTEGER PRIMARY KEY,
  post_id INTEGER NOT NULL,
  collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
  age_hours REAL DEFAULT 0,
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


def jdump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def log_event(event, details):
    with connect() as con:
        con.execute(
            "INSERT INTO system_log(event,details_json) VALUES(?,?)",
            (event, jdump(details)),
        )
