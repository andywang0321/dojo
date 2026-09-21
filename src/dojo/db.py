"""SQLite persistence for the problem bank, users, and attempts.

Schema design note: the *learner model* (attempts + schedule) is the asset.
Problems are a catalog; attempts are the durable record of what actually
happened. Keep every pedagogical signal — hints consumed, self-reported
complexity, measured complexity, review, reflection — on the attempt row.
"""

from __future__ import annotations

import json
import re
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
    discussion           TEXT,   -- JSON: post-solve chat transcript
    recall_grade         INTEGER, -- v0.11: 1..4 on warm-ups, NULL on solves
    measurement          TEXT,   -- v0.12: JSON scale-probe record + verdicts
    -- v0.13: which backend/model produced this row's AI-derived fields. A mock
    -- row and a live row were indistinguishable, so any analysis of the learner
    -- model had to filter by hand (and the reviewer's prompt changed between
    -- stages, which the scores alone cannot show).
    ai_provenance        TEXT
);

-- v0.13: every version the student submitted, with the artifacts its code
-- produced. `attempts` stays the head (every existing query keeps working); this
-- table is what makes "the original submission is lost" impossible — a submit or
-- a polish used to overwrite the single `code` column, so the version the first
-- review and the first measurement actually graded was gone.
CREATE TABLE IF NOT EXISTS attempt_revisions (
    id                 INTEGER PRIMARY KEY,
    attempt_id         INTEGER NOT NULL REFERENCES attempts(id),
    revision           INTEGER NOT NULL,   -- 1-based, per attempt
    kind               TEXT NOT NULL,      -- 'submit' | 'polish'
    code               TEXT NOT NULL,
    status             TEXT NOT NULL,      -- the judge's verdict at this revision
    judge              TEXT,               -- JSON: totals + per-case failures
    hints              TEXT,               -- JSON: the hint transcript at this point
    self_reported_time TEXT,
    self_reported_space TEXT,
    measurement        TEXT,               -- JSON: the probe record for THIS code
    static_analysis    TEXT,
    review             TEXT,               -- the review as of this revision
    reflection         TEXT,
    created_at         TEXT NOT NULL,
    UNIQUE (attempt_id, revision)
);

-- v0.13 follow-up: the memory unit is one solved **problem**, not one pattern.
-- A pattern card reported a single stability for problems with wildly different
-- ones — in the live DB it hid ten solved problems that had never been recalled
-- once, under a "34-day stable" pattern. Scheduling state lives here; `pattern`
-- stays as the rollup key for `dojo progress`.
CREATE TABLE IF NOT EXISTS item_cards (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    slug            TEXT NOT NULL,
    pattern         TEXT,
    stability       REAL NOT NULL,     -- FSRS stability, days
    difficulty      REAL NOT NULL,     -- FSRS difficulty, 1..10
    reps            INTEGER NOT NULL DEFAULT 0,
    lapses          INTEGER NOT NULL DEFAULT 0,
    due_at          TEXT NOT NULL,     -- ISO UTC; due for warm-up retrieval
    last_review_at  TEXT,
    last_reflection TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (user_id, slug)
);

-- Legacy (pre-v0.13-follow-up): one card per pattern. It is no longer written;
-- `rebuild_item_cards` replays the attempt log into `item_cards` instead, and
-- this table is kept only so nothing a student earned is destroyed.
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

#: Idempotent creation for existing DBs (v0.13) — the same statement the schema
#: above carries, reused by `migrate` so an old DB gains the table on connect.
ATTEMPT_REVISIONS_DDL = """
CREATE TABLE IF NOT EXISTS attempt_revisions (
    id                 INTEGER PRIMARY KEY,
    attempt_id         INTEGER NOT NULL REFERENCES attempts(id),
    revision           INTEGER NOT NULL,
    kind               TEXT NOT NULL,
    code               TEXT NOT NULL,
    status             TEXT NOT NULL,
    judge              TEXT,
    hints              TEXT,
    self_reported_time TEXT,
    self_reported_space TEXT,
    measurement        TEXT,
    static_analysis    TEXT,
    review             TEXT,
    reflection         TEXT,
    created_at         TEXT NOT NULL,
    UNIQUE (attempt_id, revision)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


_TABLE_DEF_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", re.DOTALL
)


def _table_bodies(schema: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _TABLE_DEF_RE.finditer(schema)}


def _addable_columns(body: str) -> dict[str, str]:
    """The columns `ALTER TABLE ... ADD COLUMN` can add from a table definition.

    Constraints and anything NOT NULL without a DEFAULT are skipped: SQLite
    cannot add those to an existing table, and pretending otherwise would fail
    at startup. What remains is exactly the shape every dojo migration has taken
    (a nullable column or one with a default)."""
    out: dict[str, str] = {}
    for raw in body.splitlines():
        line = raw.split("--", 1)[0].strip().rstrip(",")
        if not line:
            continue
        upper = line.upper()
        if upper.startswith(
            ("UNIQUE", "PRIMARY KEY", "FOREIGN KEY", "CHECK", "CONSTRAINT")
        ):
            continue
        if "UNIQUE" in upper or "PRIMARY KEY" in upper or "REFERENCES" in upper:
            continue
        if "NOT NULL" in upper and "DEFAULT" not in upper:
            continue
        out[line.split()[0]] = line
    return out


def migrate(conn: sqlite3.Connection) -> None:
    """Bring the database up to `SCHEMA`: create what is missing, add what is
    new, and never remove or retype anything (AGENTS.md rule 4 — user data is
    real).

    **Reconciliation, not a hand-kept list (v0.13).** The old version added one
    column per historical stage, which meant a DB that predated a column the list
    forgot stayed permanently short of `SCHEMA` — and nothing could notice,
    because no test compared a migrated DB with a fresh one. Now every missing
    *addable* column is added from the schema itself, so `fresh == migrated` is
    an invariant two DBs can be diffed on (`tests/test_db.py`). Still strictly
    additive: no DROP, no type change, no constraint tightening.
    """
    # 1. Every statement in SCHEMA is `IF NOT EXISTS`, so this is idempotent and
    #    it repairs a partially-created DB (the old guard only looked for the
    #    `attempts` table, so a DB with `attempts` but no `problems` was never
    #    fixed).
    conn.executescript(SCHEMA)
    # 2. Reconcile columns on the tables that already existed.
    for table, body in _table_bodies(SCHEMA).items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in _addable_columns(body).items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
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


def iso_from_epoch(epoch: float) -> str:
    """A stored timestamp for something that began at ``epoch``. v0.11: the
    attempt row is created at submit, so ``started_at`` has to come from the
    session's own start time rather than from ``now()``."""
    if not epoch:
        return now()
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


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
    """One attempt joined with its problem, for `dojo show`.

    The problem's `function_name` / `visible_tests` / `signature` ride along so
    `dojo show --clean` can project the code through the same workbench view the
    AI sees (v0.13) — that projection identifies dojo's scaffolding by comparing
    it with what dojo would render."""
    return conn.execute(
        """
        SELECT a.*, p.slug, p.title, p.difficulty, p.pattern, p.statement,
               p.function_name, p.visible_tests, p.signature
        FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.id = ?
        """,
        (attempt_id,),
    ).fetchone()


def next_revision(conn: sqlite3.Connection, attempt_id: int) -> int:
    """The 1-based number of the revision the next write will create."""
    row = conn.execute(
        "SELECT COALESCE(MAX(revision), 0) + 1 AS n FROM attempt_revisions "
        "WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()
    return int(row["n"])


def insert_revision(
    conn: sqlite3.Connection,
    attempt_id: int,
    *,
    kind: str,
    code: str,
    status: str,
    hints: str | None = None,
) -> int:
    """Append a revision — one submitted version and the judge's verdict on it.

    Called in the same transaction as the head update: an attempt and its
    revisions describe one event, and a crash between two transactions used to
    leave a graded attempt with no record of what produced it."""
    revision = next_revision(conn, attempt_id)
    conn.execute(
        """
        INSERT INTO attempt_revisions
            (attempt_id, revision, kind, code, status, hints, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (attempt_id, revision, kind, code, status, hints, now()),
    )
    return revision


#: Columns `update_revision` will write; a whitelist, so a caller cannot inject
#: a column name into the statement.
_REVISION_FIELDS = (
    "status",
    "judge",
    "self_reported_time",
    "self_reported_space",
    "measurement",
    "static_analysis",
    "review",
    "reflection",
    "hints",
)


def update_revision(
    conn: sqlite3.Connection, attempt_id: int, revision: int, **fields
) -> None:
    """Attach the artifacts a revision's own code produced (claims, measurement,
    review, static analysis). Unknown field names are a programming error."""
    unknown = set(fields) - set(_REVISION_FIELDS)
    if unknown:
        raise ValueError(f"unknown revision field(s): {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(
        f"UPDATE attempt_revisions SET {assignments} "
        "WHERE attempt_id = ? AND revision = ?",
        (*fields.values(), attempt_id, revision),
    )


def list_revisions(conn: sqlite3.Connection, attempt_id: int) -> list[sqlite3.Row]:
    """Every revision of an attempt, oldest first (backing `dojo show`)."""
    return conn.execute(
        "SELECT * FROM attempt_revisions WHERE attempt_id = ? ORDER BY revision ASC",
        (attempt_id,),
    ).fetchall()


def get_revision(
    conn: sqlite3.Connection, attempt_id: int, revision: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM attempt_revisions WHERE attempt_id = ? AND revision = ?",
        (attempt_id, revision),
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
    """Per-pattern review-score trends for `dojo progress`.

    Warm-ups are excluded (v0.13): they store a full review too, so the
    recency-weighted trend was mixing first solves with hint-free recall
    re-solves and calling the total "solves" (audit S2.14)."""
    rows = conn.execute(
        """
        SELECT p.pattern AS pattern, a.review AS review
        FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.user_id = ? AND a.status = 'correct' AND a.kind = 'solve'
          AND a.review IS NOT NULL
        ORDER BY a.id ASC
        """,
        (user_id,),
    ).fetchall()
    return trends_from_rows(
        [(r["pattern"], loads_json(r["review"], None)) for r in rows]
    )
