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


def _insert_ladder_problem(conn, slug, pattern, lc, difficulty="Easy"):
    conn.execute(
        """
        INSERT INTO problems
            (slug, title, difficulty, pattern, statement, function_name,
             visible_tests, lc_number, created_at)
        VALUES (?, ?, ?, ?, 'stmt', 'fn', ?, ?, ?)
        """,
        (
            slug,
            slug.replace("_", " ").title(),
            difficulty,
            pattern,
            dumps_json([{"args": [[]], "expected": None}]),
            lc,
            now(),
        ),
    )
    conn.commit()


def _solve(conn, user_id, slug):
    pid = conn.execute("SELECT id FROM problems WHERE slug = ?", (slug,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', datetime('now'), datetime('now'))",
        (user_id, pid),
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
    _solve(db, uid, "already_done")
    # The stack pattern has a strong card; arrays_and_hashing has none (0 = weakest).
    card = scheduler.ensure_card(db, uid, "stack")
    db.execute("UPDATE pattern_cards SET stability = 10.0 WHERE id = ?", (card["id"],))
    db.commit()

    picked = scheduler.pick_new_problem(db, uid)
    assert picked["slug"] == "two_sum"  # unsolved + weakest pattern (non-ladder fallback)
    assert picked["slug"] != "already_done"  # solved problems are excluded


# ----------------------------------------------- roadmap picks (v0.10)

def test_pick_follows_ladder_order_within_pattern(db):
    """Within a pattern, the earliest unsolved ladder problem wins —
    regardless of difficulty or title."""
    uid = get_or_create_user(db, "andy")
    _insert_ladder_problem(db, "contains_duplicate", "arrays_and_hashing", 217)
    _insert_ladder_problem(db, "group_anagrams", "arrays_and_hashing", 49)
    _solve(db, uid, "contains_duplicate")

    picked = scheduler.pick_new_problem(db, uid)
    assert picked["slug"] == "group_anagrams"  # ladder order: 217 → 242 → 1 → 49


def test_pick_hard_prereq_gate(db):
    """A pattern stays locked until its prerequisite pattern's ladder is
    complete in the bank (v0.10 hard gate)."""
    uid = get_or_create_user(db, "andy")
    _insert_ladder_problem(db, "two_sum", "arrays_and_hashing", 1)
    _insert_ladder_problem(db, "valid_palindrome", "two_pointers", 125)

    # two_pointers requires arrays_and_hashing complete → locked.
    assert scheduler.pick_new_problem(db, uid)["slug"] == "two_sum"
    _solve(db, uid, "two_sum")  # arrays ladder complete (bank-wise)
    assert scheduler.pick_new_problem(db, uid)["slug"] == "valid_palindrome"


def test_pick_skips_uncurated_ladder_rows(db):
    """An uncurated ladder problem is invisible to the ladder — the pick
    moves on instead of serving an ungradable problem."""
    uid = get_or_create_user(db, "andy")
    _insert_ladder_problem(db, "two_sum", "arrays_and_hashing", 1)
    _insert_problem(db, "custom_stats", "arrays_and_hashing")  # non-ladder fallback
    db.execute("UPDATE problems SET function_name = NULL, visible_tests = NULL WHERE slug = 'two_sum'")
    db.commit()

    picked = scheduler.pick_new_problem(db, uid)
    assert picked["slug"] == "custom_stats"


def test_pick_falls_back_after_ladder_exhausted(db):
    uid = get_or_create_user(db, "andy")
    _insert_ladder_problem(db, "two_sum", "arrays_and_hashing", 1)
    _insert_problem(db, "custom_stats", "arrays_and_hashing")
    _solve(db, uid, "two_sum")  # the only ladder problem in the bank is done

    assert scheduler.pick_new_problem(db, uid)["slug"] == "custom_stats"


def test_practice_pick_prefers_ladder_problem(db):
    """The learn-mode handoff respects the ladder within the pattern."""
    uid = get_or_create_user(db, "andy")
    _insert_ladder_problem(db, "valid_palindrome", "two_pointers", 125)
    _insert_problem(db, "custom_two_pointer", "two_pointers", difficulty="Easy")

    picked = scheduler.pick_practice_problem(db, uid, "two_pointers")
    assert picked["slug"] == "valid_palindrome"  # ladder first, not the easier custom one

    _solve(db, uid, "valid_palindrome")
    picked = scheduler.pick_practice_problem(db, uid, "two_pointers")
    assert picked["slug"] == "custom_two_pointer"  # ladder done → fallback


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
