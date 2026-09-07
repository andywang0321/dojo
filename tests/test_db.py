"""db.py read helpers backing `dojo history` and `dojo show`."""

from dojo.db import get_attempt, get_or_create_user, list_attempts, now


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
