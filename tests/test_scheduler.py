"""FSRS-4.5 scheduler: forgetting curve, card lifecycle, picks, backfill.

The update rules are pinned against hand-computed values from the published
FSRS-4.5 equations (w = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49,
0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]) — writing the numbers out
is the point: recomputing the formula here would assert nothing.
"""

from datetime import datetime, timezone

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


def _recall_at(conn, user_id, slug, when, grade):
    """A graded warm-up attempt — the event the migration replays."""
    pid = conn.execute("SELECT id FROM problems WHERE slug = ?", (slug,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, "
        "submitted_at, recall_grade) VALUES (?, ?, 'warmup', 'correct', ?, ?, ?)",
        (user_id, pid, when, when, grade),
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
    card = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack")
    # Default seeding is the "good" grade (w[2] = 2.4 days).
    assert card["stability"] == scheduler.initial_stability(3)
    assert card["due_at"] > now()
    # Age the card a day so the review sees real forgetting (R < 1).
    db.execute(
        "UPDATE item_cards SET stability = 1.0, last_review_at = datetime('now', '-1 day') "
        "WHERE id = ?",
        (card["id"],),
    )
    db.commit()
    card = db.execute("SELECT * FROM item_cards WHERE id = ?", (card["id"],)).fetchone()

    summary = scheduler.record_grade(db, card, 3)
    row = db.execute("SELECT * FROM item_cards WHERE id = ?", (card["id"],)).fetchone()
    assert row["reps"] == 1
    assert row["stability"] > 1.0
    assert summary["due_at"] > card["due_at"]
    assert summary["interval_days"] >= 1  # whole days, never a few hours

    lapsed = scheduler.record_grade(db, row, 1)
    row = db.execute("SELECT * FROM item_cards WHERE id = ?", (card["id"],)).fetchone()
    assert row["lapses"] == 1
    assert lapsed["lapsed"]


def test_card_is_seeded_from_the_grade_that_created_it(db):
    """A first solve's hint count is evidence about the pattern: it seeds
    S0/D0 instead of the flat 0.3/5.0 the old code always wrote."""
    uid = get_or_create_user(db, "andy")
    good = scheduler.ensure_item_card(db, uid, "contains_duplicate", "arrays_and_hashing", grade=3)
    assert good["stability"] == 2.4
    assert good["difficulty"] == pytest.approx(4.93, abs=0.01)
    rough = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack", grade=1)
    assert rough["stability"] == 0.4
    assert rough["difficulty"] == pytest.approx(6.81, abs=0.01)
    # The seeded stability drives the first due date: a rough first solve comes
    # back sooner than a clean one (1 day vs 2), not seven hours later.
    assert rough["due_at"] < good["due_at"]


def test_due_cards_only_overdue(db):
    uid = get_or_create_user(db, "andy")
    future = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack")  # due tomorrow
    overdue = scheduler.ensure_item_card(db, uid, "valid_palindrome", "two_pointers")
    db.execute(
        "UPDATE item_cards SET due_at = datetime('now', '-1 day') WHERE id = ?",
        (overdue["id"],),
    )
    db.commit()
    due = scheduler.due_cards(db, uid)
    assert [c["id"] for c in due] == [overdue["id"]]
    assert future["id"] not in {c["id"] for c in due}


def test_item_problem_returns_the_cards_own_problem(db):
    """Per-problem cards make the pick total: no rotation, no "which problem
    represents this pattern today" — the card names the problem (v0.13
    follow-up)."""
    uid = get_or_create_user(db, "andy")
    for slug in ("two_sum", "valid_anagram"):
        _insert_problem(db, slug, "arrays_and_hashing")
    card = scheduler.ensure_item_card(db, uid, "valid_anagram", "arrays_and_hashing")
    assert scheduler.item_problem(db, card)["slug"] == "valid_anagram"
    # Two cards in one pattern are two independent memories.
    other = scheduler.ensure_item_card(db, uid, "two_sum", "arrays_and_hashing")
    assert scheduler.item_problem(db, other)["slug"] == "two_sum"


def test_item_problem_is_none_when_the_problem_cannot_be_served(db):
    """An uncurated (or removed) problem must be visible as a curation problem,
    not deferred in silence for days (v0.13 audit, S2.11)."""
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_item_card(db, uid, "never_landed", "stack")
    assert scheduler.item_problem(db, card) is None

    _insert_problem(db, "uncurated", "stack")
    db.execute("UPDATE problems SET function_name = NULL WHERE slug = 'uncurated'")
    db.commit()
    card = scheduler.ensure_item_card(db, uid, "uncurated", "stack")
    assert scheduler.item_problem(db, card) is None


def test_pick_new_problem_weakest_pattern(db):
    uid = get_or_create_user(db, "andy")
    _insert_problem(db, "two_sum", "arrays_and_hashing")
    _insert_problem(db, "valid_parentheses", "stack")
    _insert_problem(db, "already_done", "stack")
    # Solve one problem, leave the rest unsolved.
    _solve(db, uid, "already_done")
    # The stack pattern has a strong card; arrays_and_hashing has none (0 = weakest).
    card = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack")
    db.execute("UPDATE item_cards SET stability = 10.0 WHERE id = ?", (card["id"],))
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


def test_rebuild_derives_one_card_per_solved_problem(db):
    """The migration is a replay of the attempt log, so it is total and
    idempotent: one card per solved (and still curated) problem."""
    uid = get_or_create_user(db, "andy")
    for slug in ("two_sum", "valid_anagram"):
        _insert_problem(db, slug, "arrays_and_hashing")
    _insert_problem(db, "uncurated", "arrays_and_hashing", curated=False)
    _solve(db, uid, "two_sum")
    _solve(db, uid, "valid_anagram")
    _solve(db, uid, "uncurated")

    summary = scheduler.rebuild_item_cards(db, uid)
    assert summary["cards"] == 2  # the uncurated problem cannot be served
    assert summary["never_recalled"] == 2
    cards = {c["slug"] for c in scheduler.due_cards(db, uid, limit=10)}
    assert "uncurated" not in cards
    # A replay is deterministic: running it again lands the same state.
    again = scheduler.rebuild_item_cards(db, uid)
    assert again == summary
    assert len(scheduler.due_cards(db, uid, limit=10)) == len(cards)


def test_rebuild_replays_grades_per_problem(db):
    """A warm-up's grade is that problem's (v0.11 persists it on the attempt),
    so two problems in one pattern end up with their own stability."""
    uid = get_or_create_user(db, "andy")
    for slug in ("two_sum", "valid_anagram"):
        _insert_problem(db, slug, "arrays_and_hashing")
    _solve_at(db, uid, "two_sum", "2026-08-01T00:00:00+00:00")
    _solve_at(db, uid, "valid_anagram", "2026-08-01T00:00:00+00:00")
    _recall_at(db, uid, "two_sum", "2026-08-04T00:00:00+00:00", grade=4)
    for _ in range(3):
        _recall_at(db, uid, "valid_anagram", "2026-08-04T00:00:00+00:00", grade=1)

    scheduler.rebuild_item_cards(db, uid)
    cards = {c["slug"]: c for c in db.execute("SELECT * FROM item_cards").fetchall()}
    assert cards["two_sum"]["reps"] == 1 and cards["two_sum"]["lapses"] == 0
    assert cards["valid_anagram"]["lapses"] == 3
    assert cards["two_sum"]["stability"] > cards["valid_anagram"]["stability"]


def test_rebuild_spreads_an_overdue_never_recalled_backlog(db):
    """Eight solved-but-never-recalled problems are all genuinely overdue at
    once; the rebuild spreads them so a student is not handed the whole pile in
    one session (a capacity decision, not a memory claim)."""
    uid = get_or_create_user(db, "andy")
    for i in range(7):
        _insert_problem(db, f"p{i}", "arrays_and_hashing")
        _solve_at(db, uid, f"p{i}", "2026-08-01T00:00:00+00:00")

    summary = scheduler.rebuild_item_cards(db, uid, spread_days=7)
    assert summary["spread"] == 7
    due = scheduler.due_cards(db, uid, limit=10)
    assert len(due) == 1  # only the first of the spread backlog is due today
    future = db.execute(
        "SELECT COUNT(*) AS n FROM item_cards WHERE datetime(due_at) > datetime(?)",
        (now(),),
    ).fetchone()["n"]
    assert future == 6


def test_rebuild_leaves_the_recalled_cards_alone(db):
    """Only the *overdue, never-recalled* backlog is spread: a problem with real
    recall history keeps the due date its own history earned."""
    uid = get_or_create_user(db, "andy")
    _insert_problem(db, "two_sum", "arrays_and_hashing")
    _solve_at(db, uid, "two_sum", "2026-08-01T00:00:00+00:00")
    _recall_at(db, uid, "two_sum", "2026-08-04T00:00:00+00:00", grade=4)
    summary = scheduler.rebuild_item_cards(db, uid, spread_days=7)
    assert summary["spread"] == 0
    card = db.execute("SELECT * FROM item_cards").fetchone()
    assert datetime.fromisoformat(card["due_at"]) > datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_record_grade_refuses_an_out_of_range_grade(db):
    """`max(1, min(4, …))` silently read 0 as a lapse and 5+ as "easy" (x2.61 on
    the whole grown stability) — a landmine for the next caller."""
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack")
    for bad in (0, 5, -1, 99):
        with pytest.raises(ValueError):
            scheduler.record_grade(db, card, bad)
    assert db.execute("SELECT reps FROM item_cards").fetchone()["reps"] == 0


def test_record_grade_can_defer_its_commit(db):
    """The card update and `attempts.recall_grade` describe one event; the caller
    pairs them in a single transaction so a crash cannot apply the grade twice."""
    from dojo.db import get_or_create_user, connect

    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack")
    scheduler.record_grade(db, card, 2, commit=False)
    assert db.execute("SELECT reps FROM item_cards").fetchone()["reps"] == 1
    db.rollback()
    assert db.execute("SELECT reps FROM item_cards").fetchone()["reps"] == 0


def test_due_cards_has_a_deterministic_tie_break(db):
    """Backfill gives every card the same `due_at`, so without a tie-break a
    limited fetch returned an arbitrary subset in unspecified order."""
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    for slug in ("trees", "stack", "heap"):
        scheduler.ensure_item_card(db, uid, slug, slug, due_immediately=True)
    order = [r["slug"] for r in scheduler.due_cards(db, uid)]
    assert order == ["heap", "stack", "trees"]


def _card_due_in(conn, user_id, *, hours=None, days=None, pattern="stack", slug=None):
    from datetime import datetime, timedelta, timezone

    delta = timedelta(hours=hours or 0, days=days or 0)
    due = (datetime.now(timezone.utc) + delta).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO item_cards (user_id, slug, pattern, stability, difficulty, "
        "reps, lapses, due_at, created_at) VALUES (?, ?, ?, 1.0, 5.0, 0, 0, ?, ?)",
        (user_id, slug or f"{pattern}-{due}", pattern, due, now()),
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
