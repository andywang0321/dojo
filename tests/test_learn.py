"""Learning mode (v0.8): topic resolution, the teacher conversation, the
practice handoff, and the scheduler's practice pick — all offline."""

from dojo.db import get_or_create_user, loads_json, now
from dojo.scheduler import pick_practice_problem
from dojo.session.learn import resolve_pattern, run_learn
from dojo.tutor.backend import MockBackend


def _seed_problem(db, slug, pattern, difficulty="Easy", solved=False):
    from dojo.db import dumps_json

    db.execute(
        """
        INSERT INTO problems (slug, title, difficulty, pattern, statement,
            function_name, expected_time, expected_space, visible_tests, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            f"T {slug}",
            difficulty,
            pattern,
            "Statement.",
            "solve_it",
            "O(n)",
            "O(n)",
            dumps_json([{"args": [[1]], "expected": 1}]),
            now(),
        ),
    )
    db.commit()
    if solved:
        uid = get_or_create_user(db, "andy")
        pid = db.execute("SELECT id FROM problems WHERE slug = ?", (slug,)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO attempts (user_id, problem_id, kind, status,
                started_at, submitted_at)
            VALUES (?, ?, 'solve', 'correct', ?, ?)
            """,
            (uid, pid, now(), now()),
        )
        db.commit()


# ------------------------------------------------------------ topic resolution

def test_resolve_pattern_exact_and_normalized():
    assert resolve_pattern("heap") == ("heap", None)
    assert resolve_pattern("binary search") == ("binary_search", None)
    assert resolve_pattern("  Two_Pointers ") == ("two_pointers", None)
    assert resolve_pattern("arrays  and   hashing") == ("arrays_and_hashing", None)


def test_resolve_pattern_did_you_mean():
    pattern, suggestion = resolve_pattern("heep")
    assert pattern is None
    assert suggestion == "heap"


def test_resolve_pattern_no_close_match():
    assert resolve_pattern("zzzqqq") == (None, None)


# -------------------------------------------------------------- practice pick

def test_pick_practice_problem_easiest_unsolved(db):
    _seed_problem(db, "h_easy", "heap", "Easy")
    _seed_problem(db, "h_hard", "heap", "Hard")
    _seed_problem(db, "h_solved", "heap", "Easy", solved=True)
    uid = get_or_create_user(db, "andy")
    row = pick_practice_problem(db, uid, "heap")
    assert row["slug"] == "h_easy"


def test_pick_practice_problem_nothing_available(db):
    _seed_problem(db, "h_solved", "heap", "Easy", solved=True)
    uid = get_or_create_user(db, "andy")
    assert pick_practice_problem(db, uid, "heap") is None
    assert pick_practice_problem(db, uid, "graphs") is None


# ------------------------------------------------------------ the conversation

def test_run_learn_happy_path_hands_off(db, fake_console):
    """Primer → exchanges → `practice` accepted: the transcript persists with
    roles in order, the session is marked completed, and the result carries
    the practice slug."""
    _seed_problem(db, "kth_largest", "heap", "Easy")
    console = fake_console(["why is peek O(1)?", "practice", "y"])
    backend = MockBackend(teacher=["Heap primer.", "Because the root holds the min."])

    result = run_learn(db, console, backend, "andy", "heap")
    assert result == {"practice": "kth_largest"}

    row = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert row["pattern"] == "heap"
    assert row["completed"] == 1
    transcript = loads_json(row["transcript"])
    assert [e["role"] for e in transcript] == ["teacher", "student", "teacher"]
    assert transcript[0]["text"] == "Heap primer."
    assert transcript[1]["text"] == "why is peek O(1)?"


def test_run_learn_decline_stays_then_done_ends(db, fake_console):
    _seed_problem(db, "kth_largest", "heap", "Easy")
    console = fake_console(["practice", "n", "done"])
    backend = MockBackend(teacher="Heap primer.")

    result = run_learn(db, console, backend, "andy", "heap")
    assert result == {"practice": None}
    assert "Staying in learn mode" in console.text
    row = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert row["completed"] == 1
    assert [e["role"] for e in loads_json(row["transcript"])] == ["teacher"]


def test_run_learn_handoff_slug_offers_retry(db, fake_console):
    """The in-session path: `practice` offers to retry the parked slug."""
    console = fake_console(["practice", "y"])
    backend = MockBackend(teacher="Heap primer.")

    result = run_learn(db, console, backend, "andy", "heap", handoff_slug="kth_largest")
    assert result == {"practice": "kth_largest"}
    assert "retry" in console.text.lower()


def test_run_learn_exhausted_pattern_stays_in_conversation(db, fake_console):
    """No unsolved curated problem in the pattern: `practice` says so and the
    conversation continues."""
    console = fake_console(["practice", "done"])
    backend = MockBackend(teacher="Heap primer.")

    result = run_learn(db, console, backend, "andy", "heap")
    assert result == {"practice": None}
    assert "No unsolved curated problem" in console.text


def test_learn_typo_guard_confirms_done(db, fake_console):
    console = fake_console(["don", "y"])
    backend = MockBackend(teacher="Heap primer.")
    result = run_learn(db, console, backend, "andy", "heap")
    assert result == {"practice": None}
    assert "Did you mean `done`" in console.text
    assert db.execute("SELECT completed FROM learn_sessions").fetchone()["completed"] == 1


def test_an_offline_teacher_says_the_network_and_records_nothing(db, fake_console):
    """Learn mode cannot start without the teacher — and the line says *why*,
    without implying the student has to re-learn how to type (v0.13 follow-up)."""
    from dojo.guard import network_message

    class OfflineBackend(MockBackend):
        def chat(self, role, system, user):
            raise ConnectionResetError(54, "Connection reset by peer")

    console = fake_console([])   # the primer fails before a single prompt
    result = run_learn(db, console, OfflineBackend(), "andy", "heap")

    assert result == {"practice": None}
    assert network_message() in console.text
    assert "nothing was recorded" in console.text
    assert "ConnectionResetError" not in console.text
    row = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert loads_json(row["transcript"]) == []       # no phantom teacher turn
    assert not row["completed"]
