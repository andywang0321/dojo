"""FSRS-4.5 scheduler: forgetting curve, card lifecycle, picks, backfill.

The update rules are pinned against hand-computed values from the published
FSRS-4.5 equations (w = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49,
0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]) — writing the numbers out
is the point: recomputing the formula here would assert nothing.
"""

import pytest

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
    _solve_at(conn, user_id, slug, None)


def _solve_at(conn, user_id, slug, when):
    """A correct solve, optionally with an explicit submitted_at (the warm-up
    rotation is decided by the per-problem *latest* correct attempt)."""
    pid = conn.execute("SELECT id FROM problems WHERE slug = ?", (slug,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', COALESCE(?, datetime('now')), COALESCE(?, datetime('now')))",
        (user_id, pid, when, when),
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


def test_initial_stability_and_difficulty_by_grade():
    """FSRS-4.5: S0 = w[G-1]; D0 = clamp(w4 - (G-3)·w5, 1, 10)."""
    assert [scheduler.initial_stability(g) for g in (1, 2, 3, 4)] == [0.4, 0.6, 2.4, 5.8]
    assert [
        round(scheduler.initial_difficulty(g), 2) for g in (1, 2, 3, 4)
    ] == [6.81, 5.87, 4.93, 3.99]


def test_successful_review_matches_fsrs45():
    """Hand-computed at S=1, D=5, R=0.9: good ≈ 3.6239, with the hard penalty
    (×0.29) and easy bonus (×2.61) applied to the whole grown stability."""
    assert scheduler.review(1.0, 5.0, 0.9, 3)[0] == pytest.approx(3.6239, abs=1e-3)
    assert scheduler.review(1.0, 5.0, 0.9, 2)[0] == pytest.approx(1.0509, abs=1e-3)
    assert scheduler.review(1.0, 5.0, 0.9, 4)[0] == pytest.approx(9.4584, abs=1e-3)
    assert scheduler.review(1.0, 5.0, 0.9, 3)[1] == pytest.approx(4.9993, abs=1e-3)


def test_lapse_matches_fsrs45_and_never_raises_stability():
    s, d = scheduler.review(5.0, 5.0, 0.9, 1)
    assert s == pytest.approx(1.9141, abs=1e-3)
    # D' = w7·w4 + (1-w7)·(D - w6·(G-3)) = 0.0493 + 0.99·(5 + 1.72)
    assert d == pytest.approx(6.7021, abs=1e-3)
    # min(S, ·) — a lapse can never leave a card stronger than it was.
    assert scheduler.review(0.4, 5.0, 0.9, 1)[0] <= 0.4


def test_difficulty_mean_reverts_toward_the_good_baseline():
    d = 4.93
    for _ in range(50):
        d = scheduler.review(10.0, d, 0.9, 4)[1]
    assert d == pytest.approx(1.0, abs=0.1)  # clamped, never below the floor


def test_intervals_are_whole_days_and_never_sub_day():
    """The defect this fixes: S0 = 0.3 with float intervals scheduled the
    first warm-up ~7 hours out, so cards never left the same-day regime."""
    assert scheduler.interval_days(0.4) == 1  # FSRS's floor: at least a day
    assert scheduler.interval_days(2.4) == 2
    assert scheduler.interval_days(8.03) == 8
    assert isinstance(scheduler.interval_days(2.4), int)


def test_schedule_grows_to_weeks_where_the_old_constants_stalled():
    """Three good recalls at their due dates reach ~24 days. The previous
    constants reached 1.5 days after twelve."""
    s, d = scheduler.initial_stability(3), scheduler.initial_difficulty(3)
    assert scheduler.interval_days(s) == 2
    for _ in range(2):
        s, d = scheduler.review(s, d, 0.9, 3)
    assert scheduler.interval_days(s) >= 7


def test_card_lifecycle(db):
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack")
    # Default seeding is the "good" grade (w[2] = 2.4 days).
    assert card["stability"] == scheduler.initial_stability(3)
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
    assert summary["interval_days"] >= 1  # whole days, never a few hours

    lapsed = scheduler.record_grade(db, row, 1)
    row = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert row["lapses"] == 1
    assert lapsed["lapsed"]


def test_card_is_seeded_from_the_grade_that_created_it(db):
    """A first solve's hint count is evidence about the pattern: it seeds
    S0/D0 instead of the flat 0.3/5.0 the old code always wrote."""
    uid = get_or_create_user(db, "andy")
    good = scheduler.ensure_card(db, uid, "arrays_and_hashing", grade=3)
    assert good["stability"] == 2.4
    assert good["difficulty"] == pytest.approx(4.93, abs=0.01)
    rough = scheduler.ensure_card(db, uid, "stack", grade=1)
    assert rough["stability"] == 0.4
    assert rough["difficulty"] == pytest.approx(6.81, abs=0.01)
    # The seeded stability drives the first due date: a rough first solve comes
    # back sooner than a clean one (1 day vs 2), not seven hours later.
    assert rough["due_at"] < good["due_at"]


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


def test_warmup_problem_rotates_across_problems(db):
    """v0.11 rotation. The old rule ordered *every* correct attempt by
    submitted_at and took the first — the problem solved earliest ever, a
    value that never ages. `valid_parentheses` was therefore served as the
    stack warm-up five times while other solved problems in the pattern got
    none. The pick is now per-problem (its latest attempt), so consecutive
    warm-ups rotate."""
    uid = get_or_create_user(db, "andy")
    for slug in ("two_sum", "valid_anagram"):
        _insert_problem(db, slug, "arrays_and_hashing")
    _solve_at(db, uid, "two_sum", "2024-01-01T00:00:00+00:00")
    _solve_at(db, uid, "valid_anagram", "2024-06-01T00:00:00+00:00")
    assert scheduler.warmup_problem(db, uid, "arrays_and_hashing")["slug"] == "two_sum"

    # Practising two_sum again (a warm-up, or a re-solve) makes it the most
    # recent, so the next warm-up moves on to the other problem.
    _solve_at(db, uid, "two_sum", "2026-01-01T00:00:00+00:00")
    assert (
        scheduler.warmup_problem(db, uid, "arrays_and_hashing")["slug"] == "valid_anagram"
    )
    # ...and it comes back once that one has been practised.
    _solve_at(db, uid, "valid_anagram", "2026-02-01T00:00:00+00:00")
    assert scheduler.warmup_problem(db, uid, "arrays_and_hashing")["slug"] == "two_sum"


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


def test_due_comparisons_survive_a_naive_timestamp(db):
    """Regression: due_at is TEXT, and a naive stamp ("2026-01-01 09:00:00")
    sorts *before* the ISO form dojo writes ("2026-01-01T09:00:00+00:00") because
    a space precedes "T". Comparing the raw strings therefore read a card due
    tomorrow as overdue today — a bug that only showed up when the wall clock
    made the two stamps share a date, which is exactly when a test stops
    catching it. The comparisons now go through SQLite's `datetime()`.
    """
    from datetime import datetime, timedelta, timezone

    uid = get_or_create_user(db, "andy")
    naive = (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    assert "T" not in naive  # the shape SQLite's own datetime('now') produces
    db.execute(
        "INSERT INTO pattern_cards (user_id, pattern, stability, difficulty, reps, "
        "lapses, due_at, created_at) VALUES (?, 'heap', 1.0, 5.0, 0, 0, ?, ?)",
        (uid, naive, now()),
    )
    db.commit()

    assert scheduler.due_now_count(db, uid) == 0
    assert scheduler.due_next_day_count(db, uid) == 1
    assert scheduler.due_cards(db, uid) == []


# ------------------------------------- idempotency + SQL hygiene (v0.13)


def test_record_grade_refuses_an_out_of_range_grade(db):
    """`max(1, min(4, …))` silently read 0 as a lapse and 5+ as "easy" (x2.61 on
    the whole grown stability) — a landmine for the next caller."""
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack")
    for bad in (0, 5, -1, 99):
        with pytest.raises(ValueError):
            scheduler.record_grade(db, card, bad)
    assert db.execute("SELECT reps FROM pattern_cards").fetchone()["reps"] == 0


def test_record_grade_can_defer_its_commit(db):
    """The card update and `attempts.recall_grade` describe one event; the caller
    pairs them in a single transaction so a crash cannot apply the grade twice."""
    from dojo.db import get_or_create_user, connect

    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack")
    scheduler.record_grade(db, card, 2, commit=False)
    assert db.execute("SELECT reps FROM pattern_cards").fetchone()["reps"] == 1
    db.rollback()
    assert db.execute("SELECT reps FROM pattern_cards").fetchone()["reps"] == 0


def test_due_cards_has_a_deterministic_tie_break(db):
    """Backfill gives every card the same `due_at`, so without a tie-break a
    limited fetch returned an arbitrary subset in unspecified order."""
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    for pattern in ("trees", "stack", "heap"):
        scheduler.ensure_card(db, uid, pattern, due_immediately=True)
    order = [r["pattern"] for r in scheduler.due_cards(db, uid)]
    assert order == ["heap", "stack", "trees"]


def test_backfill_counts_cards_created_and_skips_existing(db):
    from dojo.db import dumps_json, get_or_create_user, now

    uid = get_or_create_user(db, "andy")
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
        "function_name, visible_tests, created_at) VALUES "
        "('p1','P','Easy','stack','s','f',?,?)",
        (dumps_json([{"args": [[1]], "expected": 1}]), now()),
    )
    db.commit()
    pid = db.execute("SELECT id FROM problems").fetchone()["id"]
    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, "
        "submitted_at, hint_count) VALUES (?, ?, 'solve', 'correct', ?, ?, 1)",
        (uid, pid, now(), now()),
    )
    db.commit()

    assert scheduler.backfill_cards(db, uid) == 1
    assert scheduler.backfill_cards(db, uid) == 0  # idempotent, and it says so
    card = db.execute("SELECT * FROM pattern_cards").fetchone()
    # One hint means "hard" (grade 2), which raises initial difficulty above the
    # flat "good" default: the card is seeded from the solve's own evidence.
    assert card["stability"] == scheduler.initial_stability(2)
    assert card["difficulty"] > scheduler.initial_difficulty(3)


def test_warmup_problem_ignores_untimestamped_attempts(db):
    """NULL sorts first in ASC, so a correct attempt with no `submitted_at`
    pinned the same problem as the warm-up forever — the v0.11 failure mode,
    reintroduced for NULL rows."""
    from dojo.db import dumps_json, get_or_create_user, now

    uid = get_or_create_user(db, "andy")
    for slug in ("a", "b"):
        db.execute(
            "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
            "function_name, visible_tests, created_at) VALUES (?,?, 'Easy','stack','s','f',?,?)",
            (slug, slug.upper(), dumps_json([{"args": [[1]], "expected": 1}]), now()),
        )
    db.commit()
    ids = {r["slug"]: r["id"] for r in db.execute("SELECT id, slug FROM problems")}
    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', ?, NULL)",
        (uid, ids["a"], now()),
    )
    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', ?, ?)",
        (uid, ids["b"], now(), now()),
    )
    db.commit()
    picked = scheduler.warmup_problem(db, uid, "stack")
    assert picked["slug"] == "b"  # the one with a real timestamp


# ---------------------------------- honest due reporting (v0.13 follow-up)
# A real session reported "tomorrow: 1 card(s) due" and then got no warm-up the
# next morning. The card was due at 23:48 the same evening: the footer counted a
# *rolling 24 hours* and called it "tomorrow", and a morning session never sees a
# card that only comes due at night.


def _card_due_in(conn, user_id, *, hours=None, days=None, pattern="stack"):
    from datetime import datetime, timedelta, timezone

    delta = timedelta(hours=hours or 0, days=days or 0)
    due = (datetime.now(timezone.utc) + delta).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO pattern_cards (user_id, pattern, stability, difficulty, "
        "reps, lapses, due_at, created_at) VALUES (?, ?, 1.0, 5.0, 0, 0, ?, ?)",
        (user_id, pattern, due, now()),
    )
    conn.commit()


def test_the_footer_no_longer_calls_tonight_tomorrow(db):
    """The reported symptom, pinned: a card due later *today* (in the student's
    own timezone) must not be announced as tomorrow's warm-up.

    "Now" is injected and the instants are built in local terms, because "later
    today" depends on where the clock is — the first version of this test passed
    or failed by the hour it ran at."""
    from datetime import datetime, timedelta, timezone

    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    now_utc = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    local = now_utc.astimezone()
    tonight = local.replace(hour=23, minute=30).astimezone(timezone.utc)
    _card_due_in(db, uid, hours=(tonight - now_utc).total_seconds() / 3600)

    summary = scheduler.due_summary(db, uid)
    assert summary.startswith("next warm-up"), summary
    assert "later today at 23:30" in scheduler.due_phrase(tonight.isoformat(), now_utc)
    assert "tomorrow" not in scheduler.due_phrase(tonight.isoformat(), now_utc)
    assert "due now" not in summary


def test_due_summary_distinguishes_due_now_from_coming_up(db):
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    _card_due_in(db, uid, hours=-1)  # overdue
    assert "1 card(s) due now" in scheduler.due_summary(db, uid)
    _card_due_in(db, uid, days=20, pattern="heap")  # far in the future
    assert "1 card(s) due now" in scheduler.due_summary(db, uid)
    _card_due_in(db, uid, hours=-2, pattern="trees")  # a second overdue card
    assert "2 card(s) due now" in scheduler.due_summary(db, uid)


def test_next_due_returns_the_earliest_card(db):
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    _card_due_in(db, uid, days=30, pattern="stack")
    _card_due_in(db, uid, days=2, pattern="heap")
    assert scheduler.next_due(db, uid)["pattern"] == "heap"
