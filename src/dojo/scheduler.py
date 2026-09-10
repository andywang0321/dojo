"""FSRS-lite spaced repetition and problem selection.

The retention engine. Model: each (user, pattern) has a card with two
numbers — stability S (days) and difficulty D (1..10) — plus a due date.
Recall probability follows the FSRS forgetting curve

    R(t, S) = (1 + FACTOR * t / S) ** DECAY

with FSRS's FACTOR = 19/81 and DECAY = -0.5 (so R ≈ 0.90 at t = S, which is
why the default review interval equals the stability). Stability grows on
successful recalls and shrinks on lapses; difficulty moves the other way.
This is the *shape* of FSRS-4.5 with rounded constants, deliberately small:
every parameter below is documented, and the whole model is ~50 lines.

Grades follow the Anki convention: 1 = forgot, 2 = hard, 3 = good, 4 = easy.

Also here: which problem to solve next (roadmap order + prereq gate, v0.10) and which
solved problem to re-solve for a warm-up (least recently solved).
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dojo.db import now
from dojo.patterns import prereqs_of
from dojo.roadmap import load_roadmap, next_ladder_problem

FACTOR = 19 / 81  # FSRS forgetting-curve factor
DECAY = -0.5      # FSRS forgetting-curve exponent
S0 = 0.3          # initial stability, days (first review lands tomorrow)
D0 = 5.0          # initial difficulty, 1..10
TARGET_R = 0.9    # desired retrievability at the scheduled review


def retrievability(t_days: float, stability: float) -> float:
    """Probability of recall t days after the last review, for stability S."""
    t_days = max(0.0, t_days)
    return (1 + FACTOR * t_days / stability) ** DECAY


def interval_days(stability: float, target: float = TARGET_R) -> float:
    """Days until retrievability decays to ``target``: solve
    (1 + FACTOR·t/S)^DECAY = target for t. With the FSRS constants and
    target 0.9 this equals the stability itself."""
    return stability / FACTOR * (target ** (1 / DECAY) - 1)


def review(
    stability: float, difficulty: float, r: float, grade: int
) -> tuple[float, float]:
    """FSRS-lite update. Returns (new stability, new difficulty).

    Success (grade >= 2): stability grows more for easy recalls, less when
    the card is hard (D high) or already very stable (S high, the S**-0.15
    damping); difficulty eases for easy recalls, rises for hard ones.
    Lapse (grade 1): stability roughly halves, difficulty rises.
    """
    if grade == 1:
        return max(S0, stability * 0.6), min(10.0, difficulty + 1.0)

    ease = {2: 0.6, 3: 1.0, 4: 1.4}[grade]
    new_s = stability * (
        1
        + ease
        * (11 - difficulty) / 10
        * stability ** (-0.15)
        * (math.exp((1 - r) * 2.0) - 1)
    )
    new_d = max(1.0, min(10.0, difficulty - 0.2 * (grade - 3)))
    return new_s, new_d


def _due_iso(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(
        timespec="seconds"
    )


def ensure_card(
    conn: sqlite3.Connection,
    user_id: int,
    pattern: str,
    reflection: str | None = None,
    due_immediately: bool = False,
) -> sqlite3.Row:
    """Create the card for (user, pattern) if missing; optionally store the
    latest reflection. Returns the card row."""
    row = conn.execute(
        "SELECT * FROM pattern_cards WHERE user_id = ? AND pattern = ?",
        (user_id, pattern),
    ).fetchone()
    if row is None:
        due = now() if due_immediately else _due_iso(S0)
        conn.execute(
            """
            INSERT INTO pattern_cards
                (user_id, pattern, stability, difficulty, reps, lapses,
                 due_at, last_reflection, created_at)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (user_id, pattern, S0, D0, due, reflection, now()),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM pattern_cards WHERE user_id = ? AND pattern = ?",
            (user_id, pattern),
        ).fetchone()
    if reflection:
        conn.execute(
            "UPDATE pattern_cards SET last_reflection = ? WHERE id = ?",
            (reflection, row["id"]),
        )
        conn.commit()
    return row


def _parse_utc(iso: str) -> datetime:
    """Parse an ISO timestamp, assuming UTC when no offset is present
    (SQLite datetime('now', ...) produces naive strings)."""
    dt = datetime.fromisoformat(iso)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def record_grade(conn: sqlite3.Connection, card: sqlite3.Row, grade: int) -> dict:
    """Grade a warm-up recall (1-4) and update the card. Returns a summary
    dict with the new state and the humanized next-due."""
    grade = max(1, min(4, int(grade)))
    anchor = card["last_review_at"] or card["created_at"]
    t_days = max(
        0.0,
        (datetime.now(timezone.utc) - _parse_utc(anchor)).total_seconds() / 86400,
    )
    r = retrievability(t_days, card["stability"])
    new_s, new_d = review(card["stability"], card["difficulty"], r, grade)
    interval = interval_days(new_s)
    due = _due_iso(interval)
    conn.execute(
        """
        UPDATE pattern_cards SET
            stability = ?, difficulty = ?, reps = reps + 1,
            lapses = lapses + ?, due_at = ?, last_review_at = ?
        WHERE id = ?
        """,
        (new_s, new_d, 1 if grade == 1 else 0, due, now(), card["id"]),
    )
    conn.commit()
    return {
        "stability": new_s,
        "difficulty": new_d,
        "interval_days": interval,
        "due_at": due,
        "lapsed": grade == 1,
    }


def due_cards(
    conn: sqlite3.Connection, user_id: int, limit: int | None = None
) -> list[sqlite3.Row]:
    query = (
        "SELECT * FROM pattern_cards WHERE user_id = ? AND due_at <= ? "
        "ORDER BY due_at ASC"
    )
    params: list = [user_id, now()]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def warmup_problem(
    conn: sqlite3.Connection, user_id: int, pattern: str
) -> sqlite3.Row | None:
    """The solved problem to re-solve for this pattern's warm-up: the least
    recently solved correct attempt (oldest memory = most worth retrieving)."""
    return conn.execute(
        """
        SELECT p.* FROM problems p
        JOIN attempts a ON a.problem_id = p.id
        WHERE a.user_id = ? AND a.status = 'correct' AND p.pattern = ?
          AND p.function_name IS NOT NULL AND p.visible_tests IS NOT NULL
        ORDER BY a.submitted_at ASC
        LIMIT 1
        """,
        (user_id, pattern),
    ).fetchone()


@lru_cache(maxsize=1)
def _roadmap_groups() -> list[dict]:
    """The roadmap data, loaded once per process (fail loudly at import if
    the vendored file is malformed)."""
    return load_roadmap()


def _solved_lc(conn: sqlite3.Connection, user_id: int) -> set[int]:
    """LeetCode numbers of ladder problems the user has solved correctly."""
    rows = conn.execute(
        """
        SELECT p.lc_number FROM attempts a
        JOIN problems p ON p.id = a.problem_id
        WHERE a.user_id = ? AND a.status = 'correct' AND p.lc_number IS NOT NULL
        """,
        (user_id,),
    ).fetchall()
    return {r["lc_number"] for r in rows}


def _bank_lc(conn: sqlite3.Connection) -> set[int]:
    """LeetCode numbers present in the bank *and curated* — uncurated rows
    are invisible to the ladder (it never serves what it can't grade)."""
    rows = conn.execute(
        """
        SELECT lc_number FROM problems
        WHERE lc_number IS NOT NULL
          AND function_name IS NOT NULL AND visible_tests IS NOT NULL
        """
    ).fetchall()
    return {r["lc_number"] for r in rows}


def ladder_state(
    conn: sqlite3.Connection, user_id: int
) -> tuple[set[int], set[int]]:
    """(solved ladder LC numbers, curated ladder LC numbers in the bank) —
    the two sets the roadmap view and the daily picks share."""
    return _solved_lc(conn, user_id), _bank_lc(conn)


def _prereqs_satisfied(
    conn: sqlite3.Connection,
    user_id: int,
    pattern: str,
    solved: set[int],
    bank: set[int],
    groups: list[dict],
) -> bool:
    """The hard gate (v0.10): every prerequisite pattern must have no
    unsolved ladder problem left in the bank."""
    return all(
        next_ladder_problem(groups, prereq, solved, bank) is None
        for prereq in prereqs_of(pattern)
    )


def _problem_by_lc(conn: sqlite3.Connection, lc: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM problems
        WHERE lc_number = ? AND function_name IS NOT NULL
          AND visible_tests IS NOT NULL
        LIMIT 1
        """,
        (lc,),
    ).fetchone()


def pick_new_problem(
    conn: sqlite3.Connection, user_id: int
) -> sqlite3.Row | None:
    """The next problem to serve (v0.10): walk the roadmap in order, hard
    prereq gate per pattern, and serve the earliest unsolved ladder problem
    of the first eligible pattern. Problems outside the ladder (dojo's own)
    are the fallback once the ladder is exhausted — weakest pattern first,
    the v0.1 behavior."""
    groups = _roadmap_groups()
    solved = _solved_lc(conn, user_id)
    bank = _bank_lc(conn)
    for group in groups:
        pattern = group["slug"]
        if not _prereqs_satisfied(conn, user_id, pattern, solved, bank, groups):
            continue
        lc = next_ladder_problem(groups, pattern, solved, bank)
        if lc is None:
            continue
        row = _problem_by_lc(conn, lc)
        if row is not None:
            return row
    return conn.execute(
        """
        SELECT p.* FROM problems p
        WHERE p.function_name IS NOT NULL AND p.visible_tests IS NOT NULL
          AND p.lc_number IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM attempts a
              WHERE a.user_id = ? AND a.problem_id = p.id AND a.status = 'correct'
          )
        ORDER BY
          COALESCE(
              (SELECT AVG(c.stability) FROM pattern_cards c
               WHERE c.user_id = ? AND c.pattern = p.pattern),
              0.0
          ) ASC,
          CASE p.difficulty
              WHEN 'Easy' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Hard' THEN 3 ELSE 4
          END,
          p.title
        LIMIT 1
        """,
        (user_id, user_id),
    ).fetchone()


def pick_practice_problem(
    conn: sqlite3.Connection, user_id: int, pattern: str
) -> sqlite3.Row | None:
    """The learning-mode practice handoff (v0.8, ladder-aware v0.10): the
    earliest unsolved ladder problem of ``pattern``, else the easiest
    unsolved curated non-ladder problem. Returns None when the pattern is
    exhausted — the conversation should continue instead."""
    groups = _roadmap_groups()
    lc = next_ladder_problem(groups, pattern, _solved_lc(conn, user_id), _bank_lc(conn))
    if lc is not None:
        return _problem_by_lc(conn, lc)
    return conn.execute(
        """
        SELECT p.* FROM problems p
        WHERE p.pattern = ? AND p.function_name IS NOT NULL
          AND p.visible_tests IS NOT NULL AND p.lc_number IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM attempts a
              WHERE a.user_id = ? AND a.problem_id = p.id AND a.status = 'correct'
          )
        ORDER BY
          CASE p.difficulty
              WHEN 'Easy' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Hard' THEN 3 ELSE 4
          END,
          p.title
        LIMIT 1
        """,
        (pattern, user_id),
    ).fetchone()


def backfill_cards(conn: sqlite3.Connection) -> int:
    """Create a card for every (user, pattern) with a correct attempt,
    due immediately — v0.1 solves deserve a first warm-up too."""
    rows = conn.execute(
        """
        SELECT DISTINCT a.user_id, p.pattern
        FROM attempts a JOIN problems p ON p.id = a.problem_id
        WHERE a.status = 'correct' AND p.pattern IS NOT NULL
        """
    ).fetchall()
    for r in rows:
        ensure_card(conn, r["user_id"], r["pattern"], due_immediately=True)
    return len(rows)


def defer(conn: sqlite3.Connection, card: sqlite3.Row, days: float = 1.0) -> str:
    """Push a card's due date forward (e.g. no re-solvable problem found)."""
    due = _due_iso(days)
    conn.execute(
        "UPDATE pattern_cards SET due_at = ? WHERE id = ?", (due, card["id"])
    )
    conn.commit()
    return due


def humanize_due(due_iso: str) -> str:
    delta = _parse_utc(due_iso) - datetime.now(timezone.utc)
    minutes = delta.total_seconds() / 60
    if minutes < 0:
        return "overdue"
    if minutes < 60:
        return f"in {max(1, round(minutes))} minutes"
    hours = minutes / 60
    if hours < 24:
        return f"in {round(hours)} hours"
    days = hours / 24
    return f"in {round(days, 1)} days"


def due_now_count(conn: sqlite3.Connection, user_id: int) -> int:
    """Cards due right now — the `dojo` status line."""
    return conn.execute(
        "SELECT COUNT(*) AS n FROM pattern_cards WHERE user_id = ? AND due_at <= ?",
        (user_id, now()),
    ).fetchone()["n"]


def due_next_day_count(conn: sqlite3.Connection, user_id: int) -> int:
    """Cards coming due within 24 hours — the session-end footer."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(
        timespec="seconds"
    )
    return conn.execute(
        """
        SELECT COUNT(*) AS n FROM pattern_cards
        WHERE user_id = ? AND due_at > ? AND due_at <= ?
        """,
        (user_id, now(), tomorrow),
    ).fetchone()["n"]
