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
             expected_time, expected_space, visible_tests, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    (workbench / "valid_parentheses.py").write_text(SOLUTION)

    console = fake_console(
        [
            "submit",
            "O(n) because one pass over the string",
            "O(n) for the stack",
            "The key insight: the stack mirrors the opening order.",
        ]
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
    (workbench / "valid_parentheses.py").write_text(
        textwrap.dedent(
            """
            def is_valid(s: str) -> bool:
                return s.count("(") == s.count(")")
            """
        )
    )

    console = fake_console(["submit", "quit"])
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
    (workbench / "valid_parentheses.py").write_text(SOLUTION)

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
