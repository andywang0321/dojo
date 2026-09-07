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
    kind                 TEXT NOT NULL DEFAULT 'solve',  -- 'solve' | 'warmup'
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

CREATE TABLE IF NOT EXISTS pattern_cards (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    pattern         TEXT NOT NULL,
    stability       REAL NOT NULL,     -- FSRS-lite stability, days
    difficulty      REAL NOT NULL,     -- FSRS-lite difficulty, 1..10
    reps            INTEGER NOT NULL DEFAULT 0,
    lapses          INTEGER NOT NULL DEFAULT 0,
    due_at          TEXT NOT NULL,     -- ISO UTC; due for warm-up retrieval
    last_review_at  TEXT,
    last_reflection TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (user_id, pattern)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations only (AGENTS.md rule 4: user data is real)."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'attempts'"
    ).fetchone():
        return  # fresh DB; SCHEMA will create everything
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(attempts)")}
    if "kind" not in cols:
        conn.execute(
            "ALTER TABLE attempts ADD COLUMN kind TEXT NOT NULL DEFAULT 'solve'"
        )
    conn.commit()


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_or_create_user(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO users (name, created_at) VALUES (?, ?)", (name, now())
    )
    conn.commit()
    return cur.lastrowid


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_attempts(
    conn: sqlite3.Connection,
    user_id: int,
    slug: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Attempt history for one user, newest first, optionally filtered to
    one problem slug and capped. Backs `dojo history`."""
    query = """
        SELECT a.id, a.kind, a.status, a.hint_count, a.started_at,
               a.submitted_at, a.duration_seconds,
               a.self_reported_time, a.self_reported_space,
               a.measured_time_class, a.measured_time_r2,
               a.measured_space_class, a.measured_space_r2,
               a.reflection, p.slug, p.title, p.difficulty, p.pattern
        FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.user_id = ?
    """
    params: list = [user_id]
    if slug:
        query += " AND p.slug = ?"
        params.append(slug)
    query += " ORDER BY a.id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def get_attempt(conn: sqlite3.Connection, attempt_id: int) -> sqlite3.Row | None:
    """One attempt joined with its problem, for `dojo show`."""
    return conn.execute(
        """
        SELECT a.*, p.slug, p.title, p.difficulty, p.pattern, p.statement
        FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.id = ?
        """,
        (attempt_id,),
    ).fetchone()


def dumps_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads_json(value: str | None, default=None):
    if value is None:
        return default
    return json.loads(value)
