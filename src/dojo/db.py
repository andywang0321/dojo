"""SQLite persistence for the problem bank, users, and attempts.

Schema design note: the *learner model* (attempts + schedule) is the asset.
Problems are a catalog; attempts are the durable record of what actually
happened. Keep every pedagogical signal — hints consumed, self-reported
complexity, measured complexity, review, reflection — on the attempt row.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problems (
    id              INTEGER PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    difficulty      TEXT CHECK (difficulty IN ('Easy','Medium','Hard')),
    pattern         TEXT,
    statement       TEXT NOT NULL,
    function_name   TEXT,
    expected_time   TEXT,
    expected_space  TEXT,
    source          TEXT DEFAULT 'seed',
    visible_tests   TEXT,  -- JSON: [{"args": [...], "expected": ...}]
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id                   INTEGER PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(id),
    problem_id           INTEGER NOT NULL REFERENCES problems(id),
    code                 TEXT,
    status               TEXT,   -- unsolved | correct | wrong_answer | error | timed_out
    started_at           TEXT NOT NULL,
    submitted_at         TEXT,
    duration_seconds     REAL,
    hint_count           INTEGER DEFAULT 0,
    hints                TEXT,   -- JSON: [{"tier": n, "user": ..., "hint": ...}]
    self_reported_time   TEXT,
    self_reported_space  TEXT,
    measured_time_class  TEXT,
    measured_time_r2     REAL,
    measured_space_class TEXT,
    measured_space_r2    REAL,
    review               TEXT,   -- JSON from the reviewer
    reflection           TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads_json(value: str | None, default=None):
    if value is None:
        return default
    return json.loads(value)
