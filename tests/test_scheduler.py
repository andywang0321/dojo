"""FSRS-lite scheduler: forgetting curve, card lifecycle, picks, backfill."""

from dojo import scheduler
from dojo.db import dumps_json, get_or_create_user, now


def _insert_problem(conn, slug, pattern, difficulty="Easy", curated=True):
    conn.execute(
        """
        INSERT INTO problems
            (slug, title, difficulty, pattern, statement, function_name,
             visible_tests, created_at)
        VALUES (?, ?, ?, ?, 'stmt', ?, ?, ?)
        """,
        (
            slug,
            slug.replace("_", " ").title(),
            difficulty,
            pattern,
            "fn" if curated else None,
            dumps_json([{"args": [[]], "expected": None}]) if curated else None,
            now(),
        ),
    )
    conn.commit()


def test_retrievability_curve():
    assert abs(scheduler.retrievability(0.0, 1.0) - 1.0) < 1e-9
    # With FSRS constants, R(t=S) ≈ 0.90 — the design point behind interval = S.
    assert abs(scheduler.retrievability(1.0, 1.0) - 0.9) < 0.01
    assert scheduler.retrievability(10.0, 1.0) < scheduler.retrievability(1.0, 1.0)


def test_interval_equals_stability_at_default_target():
    assert abs(scheduler.interval_days(5.0) - 5.0) < 1e-9
    assert scheduler.interval_days(10.0) > scheduler.interval_days(5.0)


def test_review_updates():
    # Lapse: stability drops, difficulty rises.
    s2, d2 = scheduler.review(1.0, 5.0, 0.9, 1)
    assert s2 < 1.0 and d2 > 5.0
    # Good: stability grows, difficulty unchanged.
    s3, d3 = scheduler.review(1.0, 5.0, 0.9, 3)
    assert s3 > 1.0 and d3 == 5.0
    # Easy grows more and eases difficulty; hard grows less and raises it.
    s4, d4 = scheduler.review(1.0, 5.0, 0.9, 4)
    s2h, d2h = scheduler.review(1.0, 5.0, 0.9, 2)
    assert s4 > s3 > s2h > 1.0
    assert d4 < 5.0 < d2h


def test_card_lifecycle(db):
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack")
    assert card["stability"] == scheduler.S0
    assert card["due_at"] > now()
    # Age the card a day so the review sees real forgetting (R < 1).
    db.execute(
        "UPDATE pattern_cards SET stability = 1.0, last_review_at = datetime('now', '-1 day') "
        "WHERE id = ?",
        (card["id"],),
    )
    db.commit()
    card = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()

    summary = scheduler.record_grade(db, card, 3)
    row = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert row["reps"] == 1
    assert row["stability"] > 1.0
    assert summary["due_at"] > card["due_at"]

    lapsed = scheduler.record_grade(db, row, 1)
    row = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert row["lapses"] == 1
    assert lapsed["lapsed"]


def test_due_cards_only_overdue(db):
    uid = get_or_create_user(db, "andy")
    future = scheduler.ensure_card(db, uid, "stack")  # due tomorrow
    overdue = scheduler.ensure_card(db, uid, "two_pointers")
    db.execute(
        "UPDATE pattern_cards SET due_at = datetime('now', '-1 day') WHERE id = ?",
        (overdue["id"],),
    )
    db.commit()
    due = scheduler.due_cards(db, uid)
    assert [c["id"] for c in due] == [overdue["id"]]
    assert future["id"] not in {c["id"] for c in due}


def test_warmup_problem_least_recent(db):
    uid = get_or_create_user(db, "andy")
    for slug in ("two_sum", "valid_anagram"):
        _insert_problem(db, slug, "arrays_and_hashing")
    for slug, when in (("two_sum", "2024-01-01T00:00:00+00:00"), ("valid_anagram", "2026-01-01T00:00:00+00:00")):
        pid = db.execute("SELECT id FROM problems WHERE slug=?", (slug,)).fetchone()["id"]
        db.execute(
            "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
            "VALUES (?, ?, 'solve', 'correct', ?, ?)",
            (uid, pid, when, when),
        )
    db.commit()
    picked = scheduler.warmup_problem(db, uid, "arrays_and_hashing")
    assert picked["slug"] == "two_sum"  # least recently solved first


def test_pick_new_problem_weakest_pattern(db):
    uid = get_or_create_user(db, "andy")
    _insert_problem(db, "two_sum", "arrays_and_hashing")
    _insert_problem(db, "valid_parentheses", "stack")
    _insert_problem(db, "already_done", "stack")
    # Solve one problem, leave the rest unsolved.
    pid = db.execute("SELECT id FROM problems WHERE slug='already_done'",).fetchone()["id"]
    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', datetime('now'), datetime('now'))",
        (uid, pid),
    )
    # The stack pattern has a strong card; arrays_and_hashing has none (0 = weakest).
    card = scheduler.ensure_card(db, uid, "stack")
    db.execute("UPDATE pattern_cards SET stability = 10.0 WHERE id = ?", (card["id"],))
    db.commit()

    picked = scheduler.pick_new_problem(db, uid)
    assert picked["slug"] == "two_sum"  # unsolved + weakest pattern
    assert picked["slug"] != "already_done"  # solved problems are excluded


def test_backfill_creates_due_cards(db):
    uid = get_or_create_user(db, "andy")
    _insert_problem(db, "two_sum", "arrays_and_hashing")
    pid = db.execute("SELECT id FROM problems WHERE slug='two_sum'").fetchone()["id"]
    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', datetime('now'), datetime('now'))",
        (uid, pid),
    )
    db.commit()
    assert scheduler.backfill_cards(db) == 1
    cards = scheduler.due_cards(db, uid)
    assert len(cards) == 1 and cards[0]["pattern"] == "arrays_and_hashing"


def test_humanize_due():
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds")
    later = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(timespec="seconds")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    assert "30 minutes" in scheduler.humanize_due(soon)
    assert "3.0 days" in scheduler.humanize_due(later)
    assert scheduler.humanize_due(past) == "overdue"
