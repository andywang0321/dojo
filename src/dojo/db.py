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
    signature       TEXT,  -- JSON: "def-sig" | {"functions": {...}} | {"methods": {...}}
    lc_number       INTEGER,  -- v0.10: LeetCode number for roadmap ladder matching
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
    reflection           TEXT,
    static_analysis      TEXT,   -- JSON: radon complexity + ruff findings
    polished             INTEGER NOT NULL DEFAULT 0,  -- post-solve re-submissions
    discussion           TEXT    -- JSON: post-solve chat transcript
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

# v0.8 learning mode: one row per learn session; the transcript is rewritten
# after every exchange (crash-safe), completed flips to 1 on graceful exit.
LEARN_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS learn_sessions (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    pattern     TEXT NOT NULL,
    transcript  TEXT NOT NULL,  -- JSON: [{"role": "student"|"teacher", "text": ...}]
    created_at  TEXT NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0
);
"""

SCHEMA = SCHEMA + LEARN_SESSIONS_DDL


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations only (AGENTS.md rule 4: user data is real).
    connect() owns the schema: a fresh DB gets the full SCHEMA here, and
    existing DBs get any missing additive columns."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'attempts'"
    ).fetchone():
        conn.executescript(SCHEMA)  # fresh (or partial) DB: create everything
        conn.commit()
        return
    attempts_cols = {r["name"] for r in conn.execute("PRAGMA table_info(attempts)")}
    if "kind" not in attempts_cols:
        conn.execute(
            "ALTER TABLE attempts ADD COLUMN kind TEXT NOT NULL DEFAULT 'solve'"
        )
    if "static_analysis" not in attempts_cols:
        conn.execute("ALTER TABLE attempts ADD COLUMN static_analysis TEXT")
    if "polished" not in attempts_cols:
        conn.execute(
            "ALTER TABLE attempts ADD COLUMN polished INTEGER NOT NULL DEFAULT 0"
        )
    if "discussion" not in attempts_cols:
        conn.execute("ALTER TABLE attempts ADD COLUMN discussion TEXT")
    problems_cols = {r["name"] for r in conn.execute("PRAGMA table_info(problems)")}
    if "signature" not in problems_cols:
        conn.execute("ALTER TABLE problems ADD COLUMN signature TEXT")
    if "lc_number" not in problems_cols:
        conn.execute("ALTER TABLE problems ADD COLUMN lc_number INTEGER")
    conn.execute(LEARN_SESSIONS_DDL)  # v0.8: idempotent table creation
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


def record_learn_session(
    conn: sqlite3.Connection, user_id: int, pattern: str, transcript: list[dict]
) -> int:
    """Start a learning-mode session (v0.8) with its initial transcript.
    Returns the session id; `update_learn_transcript` rewrites the JSON as
    the conversation grows."""
    cur = conn.execute(
        """
        INSERT INTO learn_sessions (user_id, pattern, transcript, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, pattern, dumps_json(transcript), now()),
    )
    conn.commit()
    return cur.lastrowid


def update_learn_transcript(
    conn: sqlite3.Connection,
    session_id: int,
    transcript: list[dict],
    completed: bool = False,
) -> None:
    """Persist the conversation so far — called after every exchange, so a
    crash loses at most one turn. ``completed`` marks a graceful end."""
    conn.execute(
        "UPDATE learn_sessions SET transcript = ?, completed = ? WHERE id = ?",
        (dumps_json(transcript), 1 if completed else 0, session_id),
    )
    conn.commit()


def studied_patterns(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """Patterns the user has engaged with: any learn session OR any attempt
    in the pattern. One shared notion feeding the proactive offer and the
    `dojo progress` markers."""
    rows = conn.execute(
        """
        SELECT pattern FROM learn_sessions WHERE user_id = ?
        UNION
        SELECT p.pattern FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.user_id = ?
        """,
        (user_id, user_id),
    ).fetchall()
    return {r["pattern"] for r in rows}


def unstudied(conn: sqlite3.Connection, user_id: int, pattern: str | None) -> bool:
    """True when the pattern has no learn session and no attempt yet — the
    trigger for the proactive learn offer. A missing pattern is never
    offered (there is nothing coherent to teach it about)."""
    return bool(pattern) and pattern not in studied_patterns(conn, user_id)


REVIEW_DIMS = (
    "correctness",
    "approach_quality",
    "style_idiom",
    "naming",
    "edge_cases",
    "complexity_claim_check",
    "complexity_reasoning",
)


def trends_from_rows(rows) -> list[dict]:
    """(pattern, review) pairs, oldest first → per-pattern recency-weighted
    score trends. The oldest of n attempts gets weight 1, the newest n, so
    late improvement counts more than early flailing. Missing or malformed
    reviews are skipped."""
    per_pattern: dict[str, list[dict]] = {}
    for pattern, review in rows:
        if not isinstance(review, dict):
            continue
        if not all(
            isinstance(review.get(dim), dict)
            and isinstance(review[dim].get("score"), (int, float))
            for dim in REVIEW_DIMS
        ):
            continue
        per_pattern.setdefault(pattern, []).append(review)

    trends = []
    for pattern, reviews in sorted(per_pattern.items()):
        n = len(reviews)
        total_weight = sum(range(1, n + 1))
        dims = {}
        for dim in REVIEW_DIMS:
            dims[dim] = round(
                sum(reviews[i][dim]["score"] * (i + 1) for i in range(n))
                / total_weight,
                2,
            )
        overall = round(sum(dims.values()) / len(REVIEW_DIMS), 2)
        trends.append({"pattern": pattern, "solves": n, "dims": dims, "overall": overall})
    return trends


def review_trends(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """Per-pattern review-score trends for `dojo progress`."""
    rows = conn.execute(
        """
        SELECT p.pattern AS pattern, a.review AS review
        FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.user_id = ? AND a.status = 'correct' AND a.review IS NOT NULL
        ORDER BY a.id ASC
        """,
        (user_id,),
    ).fetchall()
    return trends_from_rows(
        [(r["pattern"], loads_json(r["review"], None)) for r in rows]
    )
