"""db.py read helpers backing `dojo history` and `dojo show`."""

import sqlite3

from dojo.db import (
    get_attempt,
    get_or_create_user,
    init_db,
    list_attempts,
    loads_json,
    now,
    record_learn_session,
    studied_patterns,
    unstudied,
    update_learn_transcript,
)


def _seed_problem(db) -> int:
    db.execute(
        """
        INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at)
        VALUES ('valid_parentheses', 'Valid Parentheses', 'Easy', 'stack', 's', ?)
        """,
        (now(),),
    )
    db.commit()
    return db.execute("SELECT id FROM problems WHERE slug='valid_parentheses'").fetchone()["id"]


def _add_attempt(db, user_id, problem_id, kind="solve", status="correct") -> int:
    cur = db.execute(
        """
        INSERT INTO attempts
            (user_id, problem_id, kind, status, started_at, submitted_at, hint_count, code)
        VALUES (?, ?, ?, ?, ?, ?, 2, 'def is_valid(s): return True')
        """,
        (user_id, problem_id, kind, status, now(), now()),
    )
    db.commit()
    return cur.lastrowid


def test_list_attempts_newest_first_and_filters(db):
    uid = get_or_create_user(db, "andy")
    pid = _seed_problem(db)
    _add_attempt(db, uid, pid)
    _add_attempt(db, uid, pid, kind="warmup")

    rows = list_attempts(db, uid)
    assert [r["kind"] for r in rows] == ["warmup", "solve"]  # newest first
    assert all(r["title"] == "Valid Parentheses" and r["slug"] == "valid_parentheses" for r in rows)

    assert len(list_attempts(db, uid, slug="valid_parentheses")) == 2
    assert list_attempts(db, uid, slug="nope") == []
    assert len(list_attempts(db, uid, limit=1)) == 1


def test_get_attempt_joins_problem(db):
    uid = get_or_create_user(db, "andy")
    pid = _seed_problem(db)
    aid = _add_attempt(db, uid, pid)

    row = get_attempt(db, aid)
    assert row is not None
    assert row["slug"] == "valid_parentheses"
    assert row["statement"] == "s"
    assert row["code"].startswith("def is_valid")

    assert get_attempt(db, 9999) is None


# ------------------------------------------------------------ learn_sessions

def test_learn_session_record_and_update(db):
    """A learn session starts with an empty transcript (crash-safe baseline)
    and is rewritten after each exchange; completed flips only on demand."""
    uid = get_or_create_user(db, "andy")
    sid = record_learn_session(db, uid, "heap", [])

    row = db.execute("SELECT * FROM learn_sessions WHERE id = ?", (sid,)).fetchone()
    assert row["pattern"] == "heap"
    assert row["completed"] == 0
    assert loads_json(row["transcript"]) == []

    transcript = [{"role": "teacher", "text": "A heap keeps the min at the root."}]
    update_learn_transcript(db, sid, transcript)
    row = db.execute("SELECT * FROM learn_sessions WHERE id = ?", (sid,)).fetchone()
    assert loads_json(row["transcript"]) == transcript
    assert row["completed"] == 0

    transcript.append({"role": "student", "text": "why O(1)?"})
    update_learn_transcript(db, sid, transcript, completed=True)
    row = db.execute("SELECT * FROM learn_sessions WHERE id = ?", (sid,)).fetchone()
    assert loads_json(row["transcript"]) == transcript
    assert row["completed"] == 1


def test_studied_patterns_and_unstudied(db):
    """Studied = any learn session OR any attempt in the pattern — one shared
    notion for the proactive offer and the progress markers."""
    uid = get_or_create_user(db, "andy")
    assert unstudied(db, uid, "heap") is True
    assert studied_patterns(db, uid) == set()

    record_learn_session(db, uid, "heap", [])
    assert studied_patterns(db, uid) == {"heap"}
    assert unstudied(db, uid, "heap") is False

    pid = _seed_problem(db)  # pattern 'stack'
    _add_attempt(db, uid, pid)
    assert studied_patterns(db, uid) == {"heap", "stack"}
    assert unstudied(db, uid, "stack") is False
    assert unstudied(db, uid, None) is False  # unknown pattern: never offer


def test_learn_sessions_migrates_existing_db(tmp_path):
    """An existing DB (attempts present, no learn_sessions) gains the table
    on connect — the v0.8 migration is additive."""
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE learn_sessions")
    conn.commit()
    conn.close()

    from dojo.db import connect

    with connect(db_path) as migrated:
        assert migrated.execute("SELECT 1 FROM learn_sessions LIMIT 0").fetchall() == []
