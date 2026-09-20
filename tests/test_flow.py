"""End-to-end day flow with the mock AI backend and a pre-written solution.

The solve path exercised: submit → judge → self-report → profiler → review
→ reflection → attempt persisted with every pedagogical signal.
"""

from __future__ import annotations

import json
import textwrap

import dojo.judge

from dojo import complexity
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


REFERENCE_SOURCE = textwrap.dedent(
    '''
    @reference("valid_parentheses")
    def _reference_is_valid(s: str) -> bool:
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


def _reference_is_valid(s: str) -> bool:
    """Module-level so `inspect.getsource` can find it (the gate needs source)."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            return False
    return not stack


#: Disagrees with any correct solution on the probe input. (A reference that
#: simply returned `True` would *agree*, because the valid_parentheses probe
#: input is a well-formed string — the scale probe compares one input per size,
#: so it is a free side-check rather than a substitute for the judge's cases.)
LYING_SOURCE = textwrap.dedent(
    '''
    @reference("valid_parentheses")
    def _lying_reference(s: str) -> bool:
        return False
    '''
)


def _lying_reference(s: str) -> bool:
    return False


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


class SessionState:
    """Snapshot of ``workbench/<slug>.state.json`` as it stood when a canned
    answer was typed (the FakeConsole action hook fires before the answer is
    handled). Hints and tier are *session* state since v0.11 — an attempt row
    only exists once the student submits, so a quit leaves nothing to read."""

    def __init__(self, workbench, slug="valid_parentheses"):
        self.path = workbench / f"{slug}.state.json"
        self.data = None

    def capture(self):
        self.data = json.loads(self.path.read_text())


def test_full_day_flow(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)

    _fast_probe(monkeypatch)
    # This test pins the *degradation* path: with no reference registered the
    # probe still runs (and still reports failures) but claims nothing about
    # growth. Deleting the live entry makes that explicit — the real registry
    # gains references over time, and a test that depends on their absence is a
    # trap. (It bit immediately: registering a reference for
    # valid_parentheses broke this test's premise.)
    monkeypatch.delitem(dojo.judge.REFERENCES, "valid_parentheses", raising=False)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(n) because one pass over the string",
            "O(n) for the stack",
            "",
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
    # Wiring, not classification: the pipeline probed at scale, stored the probe
    # record, and rendered a review. What the verdict *says* is tested in
    # tests/test_growth.py (the rule) and tests/test_probe.py (the measurement).
    # This problem has no registered reference in tests, so the honest verdict is
    # "no reference" and no class is claimed — which is itself the v0.12 contract.
    record = json.loads(row["measurement"])
    assert record["reference_used"] is False
    assert row["measured_time_class"] is None
    assert record["time"]["kind"] == "unreferenced"
    assert "no reference" in console.text
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

    # A submit happened (and failed), so the attempt is recorded with the
    # judge's own verdict — not a placeholder 'unsolved'.
    row = db.execute("SELECT status FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "wrong_answer"
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
    # The command list appears after output, before each prompt (virtual
    # text on TTYs; printed on non-TTYs — the path tests exercise).
    assert "Ask a question" in console.text


def test_solve_creates_pattern_card(db, fake_console, monkeypatch, tmp_path):
    """A new solve creates the pattern's card (first review due tomorrow)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(n) because one pass over the string",
            "O(n) for the stack",
            "",
            "The key insight: the stack mirrors the opening order.",
            "done",  # close the post-solve loop (FakeConsole now refuses to guess)
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


def _fast_probe(monkeypatch):
    """Shrink the scale probe's ladder so flow tests stay quick.

    The real probe still runs — the point of these tests is the pipeline, and a
    stubbed probe would stop exercising the pairing, the failure reporting, and
    the verdict wiring. The sizes are *forced*, not `setdefault`: the flow passes
    `sizes=` explicitly, so the old wrapper was silently ineffective and every
    flow test ran the full 7-size ladder with 3 repeats (42 subprocess launches
    per submit, which is also what made a timing-based assertion look attractive).
    """
    from dojo.profiler import probe as probe_mod

    real = probe_mod.run_probe

    def small(student, generator, reference=None, **kwargs):
        kwargs["sizes"] = [100, 200, 400, 800]
        kwargs["repeats"] = 1
        return real(student, generator, reference, **kwargs)

    monkeypatch.setattr("dojo.profiler.probe.run_probe", small)


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
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "3"],
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
    # v0.11: the grade — the one event the retention model exists to capture —
    # is persisted on the attempt, not just folded into the card aggregates.
    assert attempt["recall_grade"] == 3

    updated = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert updated["reps"] == 1
    assert updated["stability"] > 1.0
    assert updated["due_at"] > card["due_at"]
    assert "recall" in console.text.lower() or "Recall grade" in console.text


def test_suggested_grade_from_ladder_hints():
    """The prior for a recall grade (v0.11). Only `ladder` hints count: a
    `discussion` question is exploring, not struggling. The suggestion tops
    out at 3 — a hint-free re-solve is evidence *against* struggle, not
    evidence of ease, and FSRS's easy bonus (×2.61 on the whole grown
    stability) is far too large to claim by default."""
    from dojo.session.flow import suggested_grade

    def hint(kind):
        return {"kind": kind, "tier": 0, "user": "q", "hint": "a"}

    assert suggested_grade([]) == 3
    assert suggested_grade([hint("discussion"), hint("discussion")]) == 3
    assert suggested_grade([hint("ladder")]) == 2
    assert suggested_grade([hint("ladder"), hint("ladder")]) == 2
    assert suggested_grade([hint("ladder")] * 3) == 1  # a repeated struggle is a lapse
    # Legacy entries predate the `kind` field and were ladder responses.
    assert suggested_grade([{"tier": 0, "user": "q", "hint": "a"}]) == 2


def test_ladder_hints_not_counted_as_struggle_when_discussing():
    """The old mapping counted every hint, so a couple of conceptual
    questions during a warm-up suggested a lapse."""
    from dojo.session.flow import suggested_grade

    discussion = [{"kind": "discussion", "tier": None, "user": "why?", "hint": "a"}] * 5
    assert suggested_grade(discussion) == 3


def test_warmup_quit_records_nothing(db, fake_console, monkeypatch, tmp_path):
    """Abandoning a warm-up is 'not now', not evidence of forgetting (v0.11):
    no attempt row and no card change. A lapse is an explicit grade 1."""
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

    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0
    updated = db.execute("SELECT * FROM pattern_cards WHERE id = ?", (card["id"],)).fetchone()
    assert updated["lapses"] == 0
    assert updated["reps"] == 0
    assert updated["stability"] == 1.0
    assert updated["due_at"] == card["due_at"]


def test_repeated_solves_create_distinct_attempts(db, fake_console, monkeypatch, tmp_path):
    """Regression: state is retired on submit, so re-solving a slug must
    create a new attempt row instead of overwriting the previous one."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    answers = [
        "submit", "O(n) one pass", "O(n) stack", "",
        "The key insight: the stack.", "done",
    ]
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
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    write_solution = lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)
    first = run_day(
        db, fake_console(["submit", "O(n) one pass", "O(n) stack", "", "3"], actions={"submit": write_solution}),
        MockBackend(), "valid_parentheses", "andy", warmup=True, card=card,
    )
    assert first == "warmup_done"
    card = db.execute("SELECT * FROM pattern_cards WHERE pattern = 'stack'").fetchone()
    second = run_day(
        db, fake_console(["submit", "O(n) one pass", "O(n) stack", "", "4"], actions={"submit": write_solution}),
        MockBackend(), "valid_parentheses", "andy", warmup=True, card=card,
    )
    assert second == "warmup_done"

    rows = db.execute("SELECT id, kind, status FROM attempts ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]
    assert all(r["kind"] == "warmup" and r["status"] == "correct" for r in rows)
    assert not (workbench / "valid_parentheses.state.json").exists()


def test_quit_before_submit_records_no_attempt(db, fake_console, monkeypatch, tmp_path):
    """v0.11 lifecycle: an attempt row exists iff the student submitted.

    Quitting a session that only poked at the tool (feature checks, a quick
    look, a change of mind) leaves the learner model untouched: no row, no
    hints, no code."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    assert run_day(
        db, fake_console(["hint stuck", "quit"]), MockBackend(),
        "valid_parentheses", "andy", open_editor=False,
    ) == "quit"

    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0
    assert not (workbench / "valid_parentheses.state.json").exists()
    # Nothing is left to resume either: the next session is a fresh one.
    assert run_day(
        db, fake_console(["quit"]), MockBackend(),
        "valid_parentheses", "andy", open_editor=False,
    ) == "quit"
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0


def test_session_hints_live_in_session_state(db, fake_console, monkeypatch, tmp_path):
    """Hints and the ladder tier are session state (v0.11) — they reach the
    attempt row only on submit, and die with an abandoned session."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    snapshot = SessionState(workbench)
    run_day(
        db, fake_console(["hint stuck", "quit"], actions={"quit": snapshot.capture}),
        MockBackend(), "valid_parentheses", "andy", open_editor=False,
    )

    hints = snapshot.data["hints"]
    assert [h["user"] for h in hints] == ["stuck"]
    assert hints[0]["tier"] == 0 and hints[0]["kind"] == "ladder"
    assert snapshot.data["tier"] == 1


def test_quit_after_failed_submit_keeps_that_attempt(db, fake_console, monkeypatch, tmp_path):
    """A submit is a real attempt even when it fails — quitting afterwards
    keeps the record of the failed attempt and adds nothing."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    wrong = "def is_valid(s: str) -> bool:\n    return s.count('(') == s.count(')')\n"

    console = fake_console(
        ["submit", "quit"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(wrong)},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"

    rows = db.execute("SELECT status, code FROM attempts").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "wrong_answer"
    assert rows[0]["code"] == wrong
    assert not (workbench / "valid_parentheses.state.json").exists()


def test_resubmit_updates_the_same_attempt_row(db, fake_console, monkeypatch, tmp_path):
    """Fixing a failed submission in the same session grades the *same*
    attempt — one invocation never produces two rows."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    path = workbench / "valid_parentheses.py"
    wrong = "def is_valid(s: str) -> bool:\n    return s.count('(') == s.count(')')\n"

    console = fake_console(
        [
            "submit",                       # fails, records wrong_answer
            "submit",                       # fixed, grades the same row
            "O(n) one pass", "O(n) stack", "",
            "The key insight: the stack.",
            "done",
        ],
        actions={"submit": lambda: path.write_text(next(scripts))},
    )
    scripts = iter([wrong, SOLUTION])
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    rows = db.execute("SELECT id, status FROM attempts").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "correct"


def test_crash_resume_reuses_the_session(db, fake_console, monkeypatch, tmp_path):
    """The state file is the only resume path now (no `park` command): a
    session killed before submitting keeps its hints and its code, and the
    submit that eventually happens creates exactly one attempt."""
    from dojo.session.state import WorkbenchState, load_state, save_state

    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    path = workbench / "valid_parentheses.py"
    path.write_text(SOLUTION)  # work in progress, no submit yet

    # Simulate the interrupted session: state on disk, no attempt row.
    from dojo.db import get_or_create_user

    save_state(
        WorkbenchState(
            slug="valid_parentheses",
            user_id=get_or_create_user(db, "andy"),
            started_epoch=1_700_000_000.0,
            tier=2,
            hints=[{"kind": "ladder", "tier": 1, "user": "stuck", "hint": "..."}],
        )
    )
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0

    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "The key insight: the stack.", "done"]
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    row = db.execute("SELECT * FROM attempts").fetchone()
    assert row["hint_count"] == 1  # the resumed session's hint survived
    assert row["started_at"].startswith("2023-11-14")  # from the resumed state
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 1
    assert load_state("valid_parentheses") is None  # retired on submit


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
    assert content.startswith("#!")  # the venv shebang answers 'which Python'
    assert ".venv/bin/python" in content.splitlines()[0]
    assert "raise NotImplementedError" in content
    assert "def is_valid(s: str) -> bool:" in content  # template stub signature
    assert "pairs = {" not in content  # the old solution is gone
    assert (workbench / ".vscode" / "settings.json").exists()  # generated workspace
    # Nothing was submitted, so nothing was recorded (v0.11).
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0


def test_post_solve_loop_polish_discuss_done(db, fake_console, monkeypatch, tmp_path):
    """After the review: `polish` returns to solving (with the discussion agent
    answering), a second `submit` re-grades and updates the same attempt row, a
    question persists a post-solve conversation, `done` retires the state.

    v0.13 changed the shape: `polish` used to *be* the re-grade, which is why
    `check` and `open` disappeared after a submit (and why typing them sent the
    words to the model as questions)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(n) one pass",
            "O(n) stack",
            "",
            "The key insight: the stack.",
            "polish",
            "check",           # available again after polish (v0.13)
            "submit",          # the re-grade
            "O(n) one pass",
            "O(n) stack",
            "",
            "n",  # no second review
            "how else could I solve this?",
            "done",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "solved"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["polished"] == 1
    assert row["recall_grade"] is None  # only warm-ups carry a recall grade
    assert "Visible cases" in console.text or "visible cases" in console.text
    discussion = json.loads(row["discussion"])
    assert len(discussion) == 1
    assert discussion[0]["user"] == "how else could I solve this?"
    assert "you could" in discussion[0]["tutor"].lower()
    assert not (workbench / "valid_parentheses.state.json").exists()
    assert "Ask a question, or: polish" in console.text  # the post-solve hint (virtual text)


def test_bare_questions_and_command_words_with_text_are_hints(db, fake_console, monkeypatch, tmp_path):
    """No more 'Unknown command' friction: a bare question, and a command
    word followed by extra text ('check my solution...'), both reach the
    tutor as hints."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    snapshot = SessionState(workbench)
    console = fake_console(
        ["what is a heap", "check my solution please", "quit"],
        actions={"quit": snapshot.capture},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "Unknown command" not in console.text
    assert "visible cases passed" not in console.text  # check never ran

    # Both inputs reached the tutor as ladder hints — observable in the session
    # state, since an abandoned session leaves no attempt row (v0.11).
    hints = snapshot.data["hints"]
    assert [h["user"] for h in hints] == ["what is a heap", "check my solution please"]


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
    """`learn` abandons the in-progress solve (nothing recorded, state
    retired), runs the teacher on the problem's pattern, and returns
    'practice' on an accepted retry — the next run_day on the same slug is a
    fresh attempt with a fresh template."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(["hint stuck", "learn", "practice", "y"])
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "practice"

    # Abandoning for study records nothing — no phantom 'unsolved' row.
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0
    learn = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert learn["pattern"] == "stack"  # the current problem's pattern
    assert learn["completed"] == 1
    assert not (workbench / "valid_parentheses.state.json").exists()
    assert "Abandoned" in console.text

    # The caller loops: a fresh session on the same slug (the _cmd_day path).
    _fast_probe(monkeypatch)
    retry = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "The key insight: the stack.", "done"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(db, retry, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    rows = db.execute("SELECT id, status FROM attempts ORDER BY id").fetchall()
    assert [r["status"] for r in rows] == ["correct"]


def test_in_session_learn_named_topic(db, fake_console, monkeypatch, tmp_path):
    """`learn <topic>` teaches another pattern and still abandons the current
    solve (the handoff, if accepted, targets the same slug)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    console = fake_console(["learn heap", "done"])
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "quit"  # declined/no handoff: the day ends here

    learn = db.execute("SELECT * FROM learn_sessions").fetchone()
    assert learn["pattern"] == "heap"
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0


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
    """A warm-up is a graded recall: `learn` is unavailable there. Leaving is
    still a no-op (v0.11) — a lapse requires an explicit grade 1."""
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
    assert updated["lapses"] == 0


def test_discuss_sees_submitted_code(db, fake_console, monkeypatch, tmp_path):
    """The post-solve discussion prompt carries the submitted code — the
    model must ground on what actually ran, not guess (v0.8.1 real-session
    failure: the model inverted which implementation was active)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    class CapturingBackend(MockBackend):
        def __init__(self):
            super().__init__()
            self.chat_prompts = []

        def chat(self, role, system, user):
            self.chat_prompts.append((system, user))
            return super().chat(role, system, user)

    backend = CapturingBackend()
    console = fake_console(
        [
            "submit",
            "O(n) one pass",
            "O(n) stack",
            "",
            "The key insight.",
            "which is better?",
            "done",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(db, console, backend, "valid_parentheses", "andy", open_editor=False) == "solved"

    discussion_prompts = [u for s, u in backend.chat_prompts if "post-solve" in s.lower()]
    assert discussion_prompts, "no discussion call captured"
    assert "SUBMITTED CODE" in discussion_prompts[0]
    assert "pairs = {" in discussion_prompts[0]  # SOLUTION's distinctive line


# ------------------------------------------- double-check gate + table (v0.9.1)

def test_complexity_double_check_can_edit_time(db, fake_console, monkeypatch, tmp_path):
    """The two complexity questions stay separate, but the double-check
    gate lets the student redo either before the machine measures —
    `time` re-asks (prefilled on a TTY), Enter continues."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit",
            "O(1) because I misread the problem",
            "O(n) for the stack",
            "time",                       # edit the time answer
            "O(n) because one pass over the string",
            "",                           # accept on the second gate
            "The key insight: the stack mirrors the opening order.",
            "done",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "solved"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["self_reported_time"] == "O(n) because one pass over the string"
    assert row["self_reported_space"] == "O(n) for the stack"
    assert "Double-check" in console.text


def _verdict(kind="matches", student_class="O(n)", steps=0, trend=1.0, note=""):
    """A growth verdict as the probe would produce it."""
    from dojo.profiler import growth

    return growth.Verdict(
        kind=kind,
        trend=trend,
        student_class=student_class,
        reference_class="O(n)",
        steps=steps,
        note=note or f"grows like the reference — consistent with {student_class}",
    )


def _measurement(time=None, space=None, reference_used=True):
    from dojo.session.flow import Measurement

    return Measurement(
        slug="valid_parentheses",
        time=time or _verdict(),
        space=space or _verdict(),
        reference_used=reference_used,
    )


def _render_complexity_table(time_verdict=None, space_verdict=None, **cells) -> str:
    """Render the table through a real Console (ANSI, color forced on —
    FakeConsole only stores str(table), which is an object repr)."""
    from rich.console import Console

    from dojo.session.flow import _show_complexity_table

    defaults = {
        "expected_time": "O(n)", "expected_space": "O(n)",
        "claimed_time": "O(n)", "claimed_space": "O(n)",
        "measurement": _measurement(time=time_verdict, space=space_verdict),
    }
    defaults.update(cells)
    console = Console(
        force_terminal=True, color_system="standard", width=200, no_color=False
    )
    with console.capture() as cap:
        _show_complexity_table(console, **defaults)
    return cap.get()


def test_complexity_table_shows_the_ratio_not_r2(db):
    """The R² column is gone with the fit. The measured side is now a paired
    comparison, so the number beside it is the cost ratio against the
    reference — always available, even when no class can be named."""
    out = _render_complexity_table(
        time_verdict=_verdict(
            kind="worse", student_class="O(n^2)", steps=2, trend=64.0,
            note="grows 2 classes faster than the reference (O(n)) — grown 64.00x",
        )
    )
    assert "R²" not in out
    assert "vs reference" in out
    assert "64.00×" in out
    assert "Red cells disagree" in out  # the evidence note survives


def test_complexity_table_color_codes_matches_and_mismatches(db):
    """All three agreeing → green; a genuine disagreement → red."""
    all_match = _render_complexity_table()
    assert "\x1b[32m" in all_match  # green
    assert "\x1b[31m" not in all_match  # no red anywhere

    mismatch = _render_complexity_table(claimed_time="O(n^2)")
    assert "\x1b[31m" in mismatch  # the disagreeing time cells go red
    assert "\x1b[32m" in mismatch  # the agreeing space row stays green


def test_an_unresolved_measurement_never_reddens_a_claim(db):
    """v0.12: when the probe cannot resolve a class it says so, and an
    unresolved measurement is not evidence against the student. Reddening a
    claim on the strength of 'we could not tell' was the v0.11 defect."""
    from dojo.profiler import growth

    unresolved = growth.Verdict(
        kind=growth.UNRESOLVED,
        trend=5.0,
        student_class=None,
        reference_class="O(n)",
        steps=None,
        note="the cost ratio grown 5.00x matches no complexity class closely enough",
    )
    out = _render_complexity_table(time_verdict=unresolved)
    assert "\x1b[31m" not in out
    assert "no complexity class" in _plain(out)
    assert "5.00×" in out  # the number is still reported


def test_a_failure_at_scale_is_shown_as_failing_not_as_unresolved(db):
    from dojo.profiler import growth

    failed = growth.Verdict(
        kind=growth.FAILED,
        trend=None,
        student_class=None,
        reference_class="O(n)",
        steps=None,
        note="your code failed at n=400: ValueError: Not enough elements!",
    )
    out = _render_complexity_table(time_verdict=failed)
    assert "your code failed at n=400" in _plain(out)


def _plain(rendered: str) -> str:
    """ANSI stripped and whitespace collapsed — rich wraps long notes, so
    content assertions must not depend on where the wrap landed."""
    import re

    return re.sub(r"\s+", " ", re.sub(r"\x1b\[[0-9;]*m", "", rendered))


def test_complexity_table_names_an_incomparable_axis(db):
    """A multi-parameter claim used to fall through the comparison silently.
    It is now reported as not comparable, not as agreement."""
    out = _render_complexity_table(
        expected_time="O(n + m)", claimed_time="O(n + m)",
        time_verdict=_verdict(student_class="O(n^2)"),
    )
    assert "does not speak to a claim in other variables" in _plain(out)
    assert "\x1b[31m" not in out  # incomparable is not a disagreement


def test_polish_reasks_complexity_and_updates_claims(db, fake_console, monkeypatch, tmp_path):
    """Polish re-collects the complexity claims for the edited code
    (prefilled with the previous ones) instead of silently comparing the
    new measurement against stale claims — the reported flag bug."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    _fast_probe(monkeypatch)

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    edited = SOLUTION + "\n# polished: early exit added\n"
    console = fake_console(
        [
            "submit",
            "O(n) one pass",
            "O(n) stack",
            "",
            "The key insight: the stack.",
            "polish",
            "submit",  # v0.13: polish switches phase; submit re-grades
            "O(n) one pass, now with an early exit",
            "O(n) stack",
            "",
            "n",  # no second review
            "done",
        ],
        actions={
            "submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION),
            "polish": lambda: (workbench / "valid_parentheses.py").write_text(edited),
        },
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    assert outcome == "solved"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["polished"] == 1
    assert row["self_reported_time"] == "O(n) one pass, now with an early exit"
    assert row["self_reported_space"] == "O(n) stack"


def test_hint_renders_markdown_in_bordered_panel(db, fake_console, monkeypatch, tmp_path):
    """v0.10.4 display contract: AI prose renders as markdown inside a
    bordered Panel; stored hints keep the raw text (never flattened)."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"

    snapshot = SessionState(workbench)
    console = fake_console(
        ["what is the invariant here?", "quit"], actions={"quit": snapshot.capture}
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"

    stored = snapshot.data["hints"][0]["hint"]
    assert stored == MockBackend.TIER_RESPONSES[0]  # raw text stored, never flattened


def test_check_shows_user_prints(db, fake_console, monkeypatch, tmp_path):
    """v0.10.7: prints are debugging statements — `check` shows them."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    printing = "def is_valid(s: str) -> bool:\n    print('debug: checking', s)\n    return True\n"

    console = fake_console(
        ["check", "quit"],
        actions={"check": lambda: (workbench / "valid_parentheses.py").write_text(printing)},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "Your code printed:" in console.text
    assert "debug: checking" in console.text


def test_typo_guard_confirms_quit(db, fake_console, monkeypatch, tmp_path):
    """'qit' is confirmed, not sent to the tutor and not silently acted on."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    console = fake_console(["qit", "y"])
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "Did you mean `quit`" in console.text


def test_typo_guard_decline_sends_question_to_tutor(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")

    workbench = tmp_path / "workbench"

    snapshot = SessionState(workbench)
    console = fake_console(["qit", "n", "quit"], actions={"quit": snapshot.capture})
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert snapshot.data["hints"][0]["user"] == "qit"  # treated as a question


# ------------------------------------------- the scale probe in a session


def test_a_failure_at_scale_is_reported_and_recorded(db, fake_console, monkeypatch, tmp_path):
    """The finding that started v0.12: code that passes the judge (n <= 12) and
    then dies on a large input used to produce NULL columns and a 5/5 review.
    It is now a first-class result, with the size and the message."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    fragile = textwrap.dedent(
        """
        def is_valid(s: str) -> bool:
            if len(s) > 500:
                raise ValueError("Not enough elements!")
            pairs = {")": "(", "]": "[", "}": "{"}
            stack = []
            for ch in s:
                if ch in "([{":
                    stack.append(ch)
                elif not stack or stack.pop() != pairs[ch]:
                    return False
            return not stack
        """
    )
    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "The stack mirrors openings.", "done"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(fragile)},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    record = json.loads(row["measurement"])
    assert record["failed_at"] == 400  # the probe input is 2n characters long
    assert "ValueError" in record["failure"]
    assert "Your code failed at n=400" in console.text.replace("\n", " ")

    from dojo.profiler import growth

    assert record["time"]["kind"] == growth.FAILED


def test_a_registered_reference_yields_a_growth_verdict(
    db, fake_console, monkeypatch, tmp_path, synthetic_probe
):
    """With a reference available the probe compares growth against it; identical
    algorithms must come back as matching.

    The measurement is injected (an exact cost model) and the verdict is not: the
    wall-clock version of this test failed 33% of the time at 6-way concurrency,
    which is exactly what AGENTS.md rule 5 forbids."""
    import dojo.judge
    from dojo.judge import REFERENCES

    _seed_problem(db)
    _fast_probe(monkeypatch)
    synthetic_probe(lambda label, n: n)  # identical cost curves on both sides
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setitem(REFERENCES, "valid_parentheses", _reference_is_valid)
    monkeypatch.setattr(
        "dojo.session.flow.reference_source", lambda slug: REFERENCE_SOURCE
    )
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "The stack mirrors openings.", "done"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    record = json.loads(row["measurement"])
    assert record["reference_used"] is True
    assert record["time"]["kind"] == "matches"
    assert row["measured_time_class"] == "O(n)"  # derived from the reference
    assert all(p["ratio"] is not None for p in record["points"])
    assert dojo.judge.REFERENCES["valid_parentheses"] is _reference_is_valid


def test_an_output_mismatch_at_scale_is_reported(db, fake_console, monkeypatch, tmp_path):
    """The probe compares outputs while it is already running both — so a
    disagreement at scale is found for free. Here the reference is the wrong
    party (the real oracle disagrees with it), so the finding must be reported as
    *unconfirmed* rather than as a verdict on the student."""
    from dojo.judge import REFERENCES

    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setitem(REFERENCES, "valid_parentheses", _lying_reference)
    monkeypatch.setattr("dojo.session.flow.reference_source", lambda slug: LYING_SOURCE)
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "The stack mirrors openings.", "done"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "solved"

    record = json.loads(
        db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()["measurement"]
    )
    assert record["mismatch_at"] is not None
    assert record["mismatch_confirmed"] is False
    assert "differs from the reference" in console.text.replace("\n", " ")
    assert "dojo report" in console.text.replace("\n", " ")


# ------------------------------------- transient failures degrade (v0.13)
# `cli.main` catches only KeyboardInterrupt, so an API blip used to end a session
# with a traceback. Every AI call site now runs behind `dojo.guard`.


class FlakyBackend(MockBackend):
    """The mock, but one role raises the way a transport failure would."""

    def __init__(self, fail: str, **kwargs):
        super().__init__(**kwargs)
        self.fail = fail
        self.calls = 0

    def chat(self, role, system, user):
        self.calls += 1
        if self.fail == "chat":
            raise ConnectionError("connection reset by peer")
        return super().chat(role, system, user)

    def chat_json(self, role, system, user):
        self.calls += 1
        if self.fail == "chat_json":
            raise TimeoutError("the request timed out")
        return super().chat_json(role, system, user)


def test_a_failing_tutor_does_not_end_the_session(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "why does this fail?",                        # the tutor raises
            "submit",
            "O(n) one pass",
            "O(n) stack",
            "",
            "The stack mirrors openings.",
            "done",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    outcome = run_day(
        db, console, FlakyBackend("chat_json"), "valid_parentheses", "andy", open_editor=False
    )
    assert outcome == "solved"          # the session carried on
    assert "tutor unavailable" in console.text
    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert json.loads(row["hints"]) == []   # nothing recorded for a failed call
    assert row["status"] == "correct"


def test_a_failing_reviewer_still_records_the_attempt(db, fake_console, monkeypatch, tmp_path):
    """The review is evidence, not the grade: a reviewer outage must not cost
    the student a graded solve."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "The stack mirrors openings.", "done"],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(
        db, console, FlakyBackend("chat_json"), "valid_parentheses", "andy", open_editor=False
    ) == "solved"
    assert "reviewer unavailable" in console.text
    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "correct"
    assert row["review"] is None


def test_a_failing_discussion_tutor_does_not_end_the_session(db, fake_console, monkeypatch, tmp_path):
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "submit", "O(n) one pass", "O(n) stack", "", "The stack mirrors openings.",
            "how else could I solve this?",     # the discussion agent raises
            "done",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(
        db, console, FlakyBackend("chat"), "valid_parentheses", "andy", open_editor=False
    ) == "solved"
    assert "discussion tutor unavailable" in console.text
    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["discussion"] is None


def test_a_failed_re_review_keeps_the_previous_review(db, fake_console, monkeypatch, tmp_path):
    """A polish-time re-review that fails used to write the review back as NULL —
    destroying the only review the attempt had (audit S2.4)."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    class ReviewThenFail(MockBackend):
        def __init__(self):
            super().__init__()
            self.reviews = 0

        def chat_json(self, role, system, user):
            if "rubric" in system.lower() or "review" in system.lower():
                self.reviews += 1
                if self.reviews > 1:
                    raise ConnectionError("connection reset by peer")
            return super().chat_json(role, system, user)

    console = fake_console(
        [
            "submit", "O(n) one pass", "O(n) stack", "", "The stack mirrors openings.",
            "polish", "submit", "O(n) one pass", "O(n) stack", "y", "done", "done",
        ],
        actions={
            "submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION),
            "polish": lambda: (workbench / "valid_parentheses.py").write_text(
                SOLUTION + "\n# polished\n"
            ),
        },
    )
    assert run_day(
        db, console, ReviewThenFail(), "valid_parentheses", "andy", open_editor=False
    ) == "solved"
    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["polished"] == 1
    assert row["review"] is not None          # the first review survived
    assert json.loads(row["review"])["correctness"]["score"] == 4


def test_a_failed_submit_records_the_sessions_hints_and_duration(db, fake_console, monkeypatch, tmp_path):
    """A failed submit used to store code but hint_count=0, hints=NULL and
    duration=NULL, because only the successful path wrote them — exactly the row
    the learner model needs when it asks what struggle looks like (audit S2.3)."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    console = fake_console(
        [
            "I'm stuck",                       # a hint (tier 0, ladder)
            "submit",                          # fails: the stub raises
            "quit",
        ],
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(
            "def is_valid(s: str) -> bool:\n    raise NotImplementedError\n"
        )},
    )
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "error"           # a crash is not a wrong answer
    assert row["hint_count"] == 1
    assert json.loads(row["hints"])[0]["tier"] == 0
    assert row["duration_seconds"] is not None


def test_a_resumed_warmup_does_not_grade_the_card_twice(db, fake_console, monkeypatch, tmp_path):
    """The card update and `attempts.recall_grade` are one event. They used to be
    two commits with nothing linking them, so a crash between them let a resumed
    warm-up apply the same grade again (reps and lapses both +2) — audit S1.7."""
    from dojo import scheduler
    from dojo.db import get_or_create_user

    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)

    uid = get_or_create_user(db, "andy")
    card = scheduler.ensure_card(db, uid, "stack", due_immediately=True)

    answers = ["submit", "O(n) one pass", "O(n) stack", "", "reflection", "3"]
    console = fake_console(
        answers,
        actions={"submit": lambda: (workbench / "valid_parentheses.py").write_text(SOLUTION)},
    )
    assert run_day(
        db, console, MockBackend(), "valid_parentheses", "andy",
        open_editor=False, warmup=True, card=card,
    ) == "warmup_done"
    after_first = db.execute("SELECT reps FROM pattern_cards").fetchone()["reps"]
    attempt_id = db.execute("SELECT id FROM attempts ORDER BY id DESC LIMIT 1").fetchone()["id"]

    # Simulate the crash window: the state file survived, the grade is on the
    # row, and the same warm-up is resumed.
    from dojo.session.state import WorkbenchState, save_state

    save_state(
        WorkbenchState(
            slug="valid_parentheses", user_id=uid, kind="warmup", attempt_id=attempt_id
        )
    )
    # The resumed path re-runs the full submit pipeline, so it re-asks the
    # complexity claims (submitting again is a fresh measurement).
    console2 = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "done"], actions={}
    )
    outcome = run_day(
        db, console2, MockBackend(), "valid_parentheses", "andy",
        open_editor=False, warmup=True, card=card,
    )
    assert outcome == "warmup_done"
    assert "not grading it twice" in console2.text
    assert db.execute("SELECT reps FROM pattern_cards").fetchone()["reps"] == after_first
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 1


# ------------------------------------------- template rendering (v0.13)


def test_a_hostile_statement_still_renders_a_parsing_template(db):
    """A statement containing a triple quote, ending in a quote, or containing a
    backslash used to produce a workbench file that did not compile — reported to
    the student as a harness error on their first `check` (audit S2.7)."""
    import ast

    from dojo.db import dumps_json, now
    from dojo.session.flow import _render_template

    hostile = [
        'Return the "sum" — e.g. print("""x""") here',
        'Given x, return "y"',
        r"Match \d+ and \sum the results",
        "print('''x''')",
    ]
    for i, statement in enumerate(hostile):
        db.execute(
            "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
            "function_name, visible_tests, signature, created_at) "
            "VALUES (?, 'T', 'Easy', 'stack', ?, 'solve_it', ?, ?, ?)",
            (f"hostile_{i}", statement, dumps_json([{"args": [[1]], "expected": 1}]),
             dumps_json("(nums: list[int]) -> int"), now()),
        )
        db.commit()
        row = db.execute("SELECT * FROM problems WHERE slug = ?", (f"hostile_{i}",)).fetchone()
        source = _render_template(row)
        ast.parse(source)                       # must parse
        assert statement.splitlines()[0][:20] in source.replace("\\\\", "\\")


def test_a_broken_template_is_a_curation_problem_not_a_crash(db, fake_console, monkeypatch, tmp_path):
    """`_write_template` validates before writing, and `run_day` reports the
    problem rather than handing the student an unparseable file."""
    from dojo.db import dumps_json, now
    from dojo.session import flow

    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
        "function_name, visible_tests, signature, created_at) "
        "VALUES ('broken_sig', 'T', 'Easy', 'stack', 's', 'f', ?, ?, ?)",
        (dumps_json([{"args": [[1]], "expected": 1}]),
         dumps_json({"methods": {"go": "not-a-signature"}}), now()),
    )
    db.commit()
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    console = fake_console(["quit"])
    assert run_day(db, console, MockBackend(), "broken_sig", "andy", open_editor=False) == "error"
    assert "does not compile" in console.text
    assert not (tmp_path / "workbench" / "broken_sig.py").exists()


# -------------------------------------- attempt revisions (v0.13, report #1)
# One `code` column, overwritten by every submit and every polish: the version
# the first review and the first measurement actually graded was gone. The head
# row still moves forward; the revisions do not.


def _run_revising_session(db, fake_console, monkeypatch, tmp_path):
    """Fail once, pass, then polish — the exact sequence that used to lose the
    original submission."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    path = workbench / "valid_parentheses.py"

    stub = "def is_valid(s: str) -> bool:\n    return False\n"
    book = {"submits": 0, "polished": False}

    def prepare_submit():
        # The first submit is the failing stub, the second the real solution, and
        # the third (after polish) the polished version.
        book["submits"] += 1
        if book["submits"] == 1:
            path.write_text(stub)
        else:
            path.write_text(SOLUTION + ("\n# polished\n" if book["polished"] else ""))

    def prepare_polish():
        book["polished"] = True
        path.write_text(SOLUTION + "\n# polished\n")

    console = fake_console(
        [
            "submit",                                     # revision 1: fails
            "submit", "O(n) one pass", "O(n) stack", "", "first insight",  # revision 2
            "polish", "submit", "O(n) one pass", "O(n) stack", "", "n",    # revision 3
            "done",
        ],
        actions={"submit": prepare_submit, "polish": prepare_polish},
    )
    return (
        run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False),
        path,
    )


def test_a_polished_attempt_keeps_every_version(db, fake_console, monkeypatch, tmp_path):
    from dojo.db import list_revisions

    outcome, path = _run_revising_session(db, fake_console, monkeypatch, tmp_path)
    assert outcome == "solved"

    attempt = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    revisions = list_revisions(db, attempt["id"])
    assert len(revisions) == 3
    assert [r["revision"] for r in revisions] == [1, 2, 3]
    assert revisions[0]["status"] == "wrong_answer"      # the original submission
    assert revisions[1]["status"] == "correct"
    assert revisions[2]["kind"] == "polish"
    assert "return False" in revisions[0]["code"]        # revision 1 is intact
    assert revisions[1]["code"] != revisions[2]["code"]  # polish appended its own
    # The head still points at the newest version, so old queries keep working —
    # and it holds the *raw* artifact, because that is what the judge ran and
    # what `dojo show --code` promises.
    assert attempt["code"] == revisions[2]["code"]
    assert attempt["code"] == path.read_text()  # exactly what the judge ran
    # Artifacts attach to the revision that produced them.
    assert revisions[0]["review"] is None
    assert revisions[1]["review"] is not None
    assert revisions[1]["measurement"] is not None


def test_the_revision_judge_record_names_the_failures(db, fake_console, monkeypatch, tmp_path):
    import json as _json

    from dojo.db import list_revisions

    _run_revising_session(db, fake_console, monkeypatch, tmp_path)
    attempt = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    first = list_revisions(db, attempt["id"])[0]
    judge = _json.loads(first["judge"])
    assert judge["status"] == "wrong_answer"
    assert judge["passed"] < judge["total"]
    assert judge["failures"] and judge["failures"][0]["label"]


def test_a_polish_does_not_touch_the_original_review(db, fake_console, monkeypatch, tmp_path):
    """The review of revision 2 stays revision 2's, even after a later polish
    re-reviews the code (audit S2.4 is the same bug from the other direction)."""
    import json as _json

    from dojo.db import list_revisions

    _run_revising_session(db, fake_console, monkeypatch, tmp_path)
    attempt = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    revisions = list_revisions(db, attempt["id"])
    assert _json.loads(revisions[1]["review"])["correctness"]["score"] == 4
    assert revisions[2]["review"] is not None      # the polish was re-reviewed


# ------------------------------------------- the phase model (v0.13, report #2)
# Two loops became one: a `phase` decides which commands exist and which agent
# answers a question. `polish` is a *mode switch* back to solving, not an alias
# for re-grading — and `check`/`open` are never silently sent to the model as
# questions again.


def _solved_session(db, fake_console, monkeypatch, tmp_path, post_answers):
    """A session that passes the first submit, then runs `post_answers` in the
    post-solve phase. Returns (console, workbench path)."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    path = workbench / "valid_parentheses.py"
    console = fake_console(
        ["submit", "O(n) one pass", "O(n) stack", "", "the stack", *post_answers],
        actions={"submit": lambda: path.write_text(SOLUTION)},
    )
    outcome = run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False)
    return outcome, console, path


def test_a_solving_command_in_the_post_solve_phase_is_explained_not_asked(
    db, fake_console, monkeypatch, tmp_path
):
    """Typing `check` after a submit used to send the literal word to the
    discussion model and run nothing. It still is not a post-solve command — the
    fix is that dojo now says so, and `polish` is the way back."""
    outcome, console, path = _solved_session(
        db, fake_console, monkeypatch, tmp_path, ["check", "done"]
    )
    assert outcome == "solved"
    assert "solving-mode command" in console.text
    # The word never reached the model as a question.
    assert "STUDENT: check" not in console.text


def test_polish_returns_to_solving_with_the_discussion_agent(
    db, fake_console, monkeypatch, tmp_path
):
    """The user's reading of `polish`: take me back to solving, but keep the
    post-solve tutor answering (the boundary lifted at the first grade)."""
    _seed_problem(db)
    _fast_probe(monkeypatch)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True)
    path = workbench / "valid_parentheses.py"

    class Recording(MockBackend):
        def __init__(self):
            super().__init__()
            self.prompts: list[str] = []

        def chat(self, role, system, user):
            self.prompts.append(system)
            return super().chat(role, system, user)

    backend = Recording()
    console = fake_console(
        [
            "submit", "O(n) one pass", "O(n) stack", "", "the stack",
            "polish",
            "check",                                   # available again
            "is a hash map faster here?",              # a question, post-polish
            "quit",                                    # keeps the attempt
        ],
        actions={"submit": lambda: path.write_text(SOLUTION)},
    )
    outcome = run_day(db, console, backend, "valid_parentheses", "andy", open_editor=False)

    assert outcome == "quit"
    assert "Back to solving" in console.text
    assert "visible cases" in console.text          # `check` ran for real
    assert any("post-solve" in system.lower() for system in backend.prompts), (
        "the question during polish must reach the discussion agent"
    )
    row = db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "correct"               # the attempt survived the quit
    assert row["discussion"] is not None
    assert not (workbench / "valid_parentheses.state.json").exists()


def test_quit_before_submitting_still_records_nothing(db, fake_console, monkeypatch, tmp_path):
    """The v0.11 rule is unchanged, and the message has to stay true: with no
    attempt, `quit` abandons; with one, it only ends the session."""
    _seed_problem(db)
    monkeypatch.setattr("dojo.session.flow.WORKBENCH_DIR", tmp_path / "workbench")
    monkeypatch.setattr("dojo.session.state.WORKBENCH_DIR", tmp_path / "workbench")
    (tmp_path / "workbench").mkdir(parents=True)
    console = fake_console(["quit"])
    assert run_day(db, console, MockBackend(), "valid_parentheses", "andy", open_editor=False) == "quit"
    assert "nothing recorded" in console.text
    assert db.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 0
