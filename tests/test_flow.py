"""End-to-end day flow with the mock AI backend and a pre-written solution.

The solve path exercised: submit → judge → self-report → profiler → review
→ reflection → attempt persisted with every pedagogical signal.
"""

from __future__ import annotations

import json
import textwrap

from dojo.session.flow import run_day
from dojo.tutor.backend import MockBackend

SOLUTION = textwrap.dedent(
    '''
    def is_valid(s: str) -> bool:
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in "([{":
                stack.append(ch)
            elif not stack or stack.pop() != pairs[ch]:
                return False
        return not stack
    '''
)


def _seed_problem(conn):
    from dojo.db import dumps_json, now

    conn.execute(
        """
        INSERT INTO problems
            (slug, title, difficulty, pattern, statement, function_name,
             expected_time, expected_space, visible_tests, signature, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "valid_parentheses",
            "Valid Parentheses",
            "Easy",
            "stack",
            "Return true if the bracket string is valid.",
            "is_valid",
            "O(n)",
            "O(n)",
            dumps_json(
                [
                    {"args": ["()"], "expected": True},
                    {"args": ["(]"], "expected": False},
                ]
            ),
            dumps_json("(s: str) -> bool"),
            now(),
        ),
    )
    conn.commit()


def test_full_day_flow(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)

    # Shrink profiler sizes so the test stays fast.
    from dojo.profiler import measure as real_measure

    def fast_measure(code_path, function_name, input_generator, **kwargs):
        return real_measure(
            code_path, function_name, input_generator,
            sizes=[100, 200, 400, 800, 1600], repeats=3,
        )

    monkeypatch.setattr("dojo.session.flow.measure", fast_measure)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(n) because one pass over the string",
            "O(n) for the stack",
            "The key insight: the stack mirrors the opening order.",
            "done",
        ],
        actions={
            # Sessions start blank now; "editing" happens during the session.
            "submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)
        },
    )

    outcome = run_day(
        db,
        console,
        MockBackend(),
        "valid_parentheses",
        "andy",
        open_editor=False,
    )
    assert outcome == "solved"

    row = db.execute(
        "SELECT * FROM attempts WHERE problem_id = (SELECT id FROM problems WHERE slug='valid_parentheses')"
    ).fetchone()
    assert row["status"] == "correct"
    assert row["self_reported_time"].startswith("O(n)")
    assert row["measured_time_class"] == "O(n)"
    assert row["measured_time_r2"] is not None and row["measured_time_r2"] > 0.8
    assert row["measured_space_class"] == "O(n)"
    review = json.loads(row["review"])
    assert "broader_picture" in review
    assert "stack" in review["broader_picture"].lower() or "LIFO" in review["broader_picture"]


def test_wrong_solution_keeps_session_open(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        ["submit", "quit"],
        actions={
            "submit": lambda: (workbench / "valid_parentheses.py").write_text(
                textwrap.dedent(
                    """
                    def is_valid(s: str) -> bool:
                        return s.count("(") == s.count(")")
                    """
                )
            )
        },
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "quit"

    row = db.execute("SELECT status FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "unsolved"
    assert any("generated" in line for line in console.text.splitlines())


def test_open_command_and_commands_hint(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    calls: list[str] = []
    monkeypatch.setattr(
        "dojo.session.flow.launch_editor",
        lambda path: calls.append(str(path)) or "opened in a window",
    )

    console = fake_console(["open", "quit"])
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "quit"
    # No auto-open: the only launch comes from the explicit `open` command.
    assert len(calls) == 1 and calls[0].endswith("valid_parentheses.py")
    assert "opened in a window" in console.text
    # The command list appears after output, before each prompt.
    assert "Commands:" in console.text
    assert console.text.count("Commands:") >= 1


def test_solve_creates_pattern_card(db, fake_console, monkeypatch, tmp_path):
    """A new solve creates the pattern's card (first review due tomorrow)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.flow.measure", _fast_measure)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(n) because one pass over the string",
            "O(n) for the stack",
            "The key insight: the stack mirrors the opening order.",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "solved"

    attempt = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert attempt["kind"] == "solve"
    card = db.execute(
        "SELECT * FROM pattern_cards WHERE pattern = 'stack'"
    ).fetchone()
    assert card is not None
    assert "stack" in card["last_reflection"]
    assert card["due_at"] > card["created_at"]  # first review scheduled in the future


def _fast_measure(code_path, function_name, input_generator, **kwargs):
    from dojo.profiler import measure as real_measure

    return real_measure(
        code_path, function_name, input_generator, sizes=[100, 200, 400, 800], repeats=2
    )


def test_warmup_flow_records_card_grade(db, fake_console, monkeypatch, tmp_path):
    from dojo import scheduler
    from dojo.db import get_or_create_user

    _seed_problem(db)
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack", due_immediately=True)
    # Age the card a day so the review has a real R < 1 and stability moves.
    db.execute(
        "UPDATE pattern_cards SET stability = 1.0, last_review_at = datetime('now', '-1 day') WHERE id = ?",
        (card["id"],),
    )
    db.commit()
    card = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()

    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.flow.measure", _fast_measure)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "3"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    outcome = run_day(
        db, console, MockBackend(), "valid_parentheses", "andy",
        open_editor=False, warmup=True, card=card,
    )
    assert outcome == "warmup_done"

    attempt = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert attempt["kind"] == "warmup"
    assert attempt["reflection"] is None  # the recall grade replaces reflection

    updated = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert updated["reps"] == 1
    assert updated["stability"] > 1.0
    assert updated["due_at"] > card["due_at"]
    assert "recall" in console.text.lower() or "Recall grade" in console.text


def test_warmup_quit_records_lapse(db, fake_console, monkeypatch, tmp_path):
    from dojo import scheduler
    from dojo.db import get_or_create_user

    _seed_problem(db)
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack", due_immediately=True)
    db.execute("UPDATE pattern_cards SET stability = 1.0 WHERE id = ?", (card["id"],))
    db.commit()

    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    console = fake_console(["quit"])
    outcome = run_day(
        db, console, MockBackend(), "valid_parentheses", "andy",
        open_editor=False, warmup=True, card=card,
    )
    assert outcome == "quit"

    updated = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert updated["lapses"] == 1
    assert updated["stability"] < 1.0


def test_repeated_solves_create_distinct_attempts(db, fake_console, monkeypatch, tmp_path):
    """Regression: state is retired on submit, so re-solving a slug must
    create a new attempt row instead of overwriting the previous one."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.flow.measure", _fast_measure)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    answers = ["submit", "O(n) one pass", "O(n) stack", "The key insight: the stack."]
    write_solution = lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)
    assert run_day(db, fake_console(answers, actions={"submit": write_solution}), MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"
    assert run_day(db, fake_console(answers, actions={"submit": write_solution}), MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    rows = db.execute("SELECT id, kind, status FROM attempts ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]
    assert all(r["kind"] == "solve" and r["status"] == "correct" for r in rows)
    assert not (workbench / "valid_parentheses.state.json").exists()


def test_repeated_warmups_create_distinct_attempts(db, fake_console, monkeypatch, tmp_path):
    """Regression: consecutive warm-ups of the same slug must not clobber
    the previous warm-up's attempt row (the original data-loss bug)."""
    from dojo import scheduler
    from dojo.db import get_or_create_user

    _seed_problem(db)
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack", due_immediately=True)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.flow.measure", _fast_measure)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    write_solution = lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)
    first = run_day(
        db, fake_console(["submit", "O(n) one pass", "O(n) stack", "3"], actions={"submit": write_solution}),
        MockBackend(), "valid_parentheses", "andy", warmup=True, card=card,
    )
    assert first == "warmup_done"
    card = db.execute("SELECT * FROM pattern_cards WHERE pattern = 'stack'").fetchone()
    second = run_day(
        db, fake_console(["submit", "O(n) one pass", "O(n) stack", "4"], actions={"submit": write_solution}),
        MockBackend(), "valid_parentheses", "andy", warmup=True, card=card,
    )
    assert second == "warmup_done"

    rows = db.execute("SELECT id, kind, status FROM attempts ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]
    assert all(r["kind"] == "warmup" and r["status"] == "correct" for r in rows)
    assert not (workbench / "valid_parentheses.state.json").exists()


def test_quit_persists_hints_and_retires_state(db, fake_console, monkeypatch, tmp_path):
    """Quitting ends the session: code and hints land on the abandoned
    attempt row, the state file is retired, and the next run starts fresh."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    # One hint (vague message → tier 0), then quit.
    assert run_day(db, fake_console(["hint stuck", "quit"]), MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "unsolved"
    assert row["hint_count"] == 1
    assert json.loads(row["hints"])[0]["tier"] == 0
    assert json.loads(row["hints"])[0]["kind"] == "ladder"
    assert not (workbench / "valid_parentheses.state.json").exists()

    # Next session is a fresh attempt, not a resume.
    assert run_day(db, fake_console(["quit"]), MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    attempts = db.execute("SELECT id FROM attempts ORDER BY id").fetchall()
    assert len(attempts) == 2
    assert attempts[0]["id"] != attempts[1]["id"]


def test_new_session_starts_from_blank_template(db, fake_console, monkeypatch, tmp_path):
    """Every new session overwrites the workbench with a blank template —
    previous solutions live on attempt rows, not in the workbench file."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    path = workbench / "valid_parentheses.py"
    path.write_text(SOLUTION)  # leftover from a previous session

    assert run_day(db, fake_console(["quit"]), MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"

    content = path.read_text()
    assert "raise NotImplementedError" in content
    assert "def is_valid(s: str) -> bool:" in content  # template stub signature
    assert "pairs = {" not in content  # the old solution is gone
    row = db.execute("SELECT code FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert "raise NotImplementedError" in row["code"]  # blank start is recorded


def test_post_solve_loop_polish_discuss_done(db, fake_console, monkeypatch, tmp_path):
    """After the review: `polish` re-grades and updates the same attempt row,
    `discuss` persists a post-solve conversation, `done` retires the state."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.flow.measure", _fast_measure)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(n) one pass",
            "O(n) stack",
            "The key insight: the stack.",
            "polish",
            "n",  # no second review
            "discuss how else could I solve this?",
            "done",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "solved"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["polished"] == 1
    discussion = json.loads(row["discussion"])
    assert len(discussion) == 1
    assert discussion[0]["user"] == "how else could I solve this?"
    assert "you could" in discussion[0]["tutor"].lower() or len(discussion[0]["tutor"]) > 0
    assert not (workbench / "valid_parentheses.state.json").exists()
    assert "Post-solve" in console.text


def test_bare_questions_and_command_words_with_text_are_hints(db, fake_console, monkeypatch, tmp_path):
    """No more 'Unknown command' friction: a bare question, and a command
    word followed by extra text ('check my solution...'), both reach the
    tutor as hints."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(["what is a heap", "check my solution please", "quit"])
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "Unknown command" not in console.text
    assert "visible cases passed" not in console.text  # check never ran

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    hints = json.loads(row["hints"])
    assert [h["user"] for h in hints] == ["what is a heap", "check my solution please"]
    assert row["hint_count"] == 2


def test_check_shows_static_findings(db, fake_console, monkeypatch, tmp_path):
    """Static analysis is advisory at check time: lint findings appear with
    the visible-test run, so the student can fix them before submitting."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    linty = "import sys\n\n" + SOLUTION

    console = fake_console(
        ["check", "quit"],
        actions={"check": lambda: (workbench / "valid_parentheses.py").write_text(linty)},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "Static analysis" in console.text
    assert "F401" in console.text


# --------------------------------------------------- in-session learn (v0.8)

def test_in_session_learn_parks_and_hands_back(db, fake_console, monkeypatch, tmp_path):
    """`learn` parks the attempt (code + hints saved, state retired, row
    'unsolved'), runs the teacher on the problem's pattern, and returns
    'practice' on an accepted retry — the next run_day on the same slug is a
    fresh attempt."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(["hint stuck", "learn", "practice", "y"])
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "practice"

    parked = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert parked["status"] == "unsolved"
    assert parked["hint_count"] == 1
    learn = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert learn["pattern"] == "stack"  # the current problem's pattern
    assert learn["completed"] == 1
    assert not (workbench / "valid_parentheses.state.json").exists()
    assert "Paused for learning" in console.text

    # The caller loops: a fresh session on the same slug (the _cmd_day path).
    monkeypatch.setattr("dojo.session.flow.measure", _fast_measure)
    retry = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "The key insight: the stack.", "done"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(db, retry, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    rows = db.execute("SELECT id, status FROM attempts ORDER BY id").fetchall()
    assert [r["status"] for r in rows] == ["unsolved", "correct"]


def test_in_session_learn_named_topic(db, fake_console, monkeypatch, tmp_path):
    """`learn <topic>` teaches another pattern but still parks the current
    attempt (the handoff, if accepted, targets the parked slug)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    console = fake_console(["learn heap", "done"])
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "quit"  # declined/no handoff: the day ends here

    learn = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert learn["pattern"] == "heap"
    parked = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert parked["status"] == "unsolved"


def test_in_session_learn_typo_stays_in_session(db, fake_console, monkeypatch, tmp_path):
    """A typo'd topic must not park the attempt: did-you-mean shows and the
    session continues."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    console = fake_console(["learn heep", "quit"])
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "did you mean" in console.text
    assert db.execute("SELECT COUNT(*) AS n FROM learn_sessions").fetchone()["n"] == 0


def test_warmup_rejects_learn(db, fake_console, monkeypatch, tmp_path):
    """A warm-up is a graded recall: `learn` is unavailable there (leaving a
    warm-up is a lapse via quit, not a pause for study)."""
    from dojo import scheduler
    from dojo.db import get_or_create_user

    _seed_problem(db)
    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack", due_immediately=True)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    console = fake_console(["learn", "quit"])
    assert run_day(
        db, console, MockBackend(), "valid_parentheses", "andy",
        open_editor=False, warmup=True, card=card,
    ) == "quit"
    assert "isn't available" in console.text
    assert db.execute("SELECT COUNT(*) AS n FROM learn_sessions").fetchone()["n"] == 0
    updated = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert updated["lapses"] == 1
