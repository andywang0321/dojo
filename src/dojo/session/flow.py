"""The daily flow: one problem, end to end.

  solve in $EDITOR (via `open`, non-blocking) → check (visible tests)
  → hint ladder → learn (park + teach the pattern, optional retry handoff)
  → submit → judge (visible + generated + oracle)
  → self-report complexity → empirical profiler → three-way complexity table
  → AI review → reflection → persist attempt

Every pedagogical signal lands on the attempt row: hint count and
transcript, self-reported vs. measured vs. expected complexity, the review,
and the reflection.
"""

from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dojo import complexity, scheduler, static
from dojo.config import VENV_PYTHON, WORKBENCH_DIR
from dojo.db import dumps_json, get_or_create_user, iso_from_epoch, loads_json, now
from dojo.editor import ensure_ide_config, launch as launch_editor
from dojo.judge import JUDGE_CASES, ORACLES, PROFILER_INPUTS, run_cases
from dojo.profiler import classify, measure, staircase_safe_points
from dojo.render import render_ai, review_markdown
from dojo.session.learn import resolve_pattern, run_learn
from dojo.session.state import (
    WorkbenchState,
    load_state,
    retire_state,
    save_state,
)
from dojo.terminal import confirm_typo, make_prompt, patch_console
from dojo.tutor import TIER_NAMES, ask_tutor, review
from dojo.tutor.prompts import DISCUSSION_SYSTEM, build_discussion_prompt
from dojo.ui import table as ui_table

GENERATED_CASES = 30

COMMANDS_HINT = "Ask a question, or: open · check · learn · submit · quit"

POST_COMMANDS_HINT = "Ask a question, or: polish · done"

TEMPLATE_STUB_COMMENT = (
    "# Solve it. Use `dojo check` / `dojo hint` from a second terminal."
)


def _render_template(problem: sqlite3.Row) -> str:
    """The blank-template stub for a problem, per its stored signature JSON:
    a plain string renders one function; {"functions": {...}} renders several;
    {"methods": {...}} renders a class. The file opens with a shebang pointing
    at dojo's venv — editors and debuggers read it to answer 'which Python'
    (v0.10.6); it self-heals because every new session rewrites the file."""
    shebang = f"#!{VENV_PYTHON}\n"
    signature = loads_json(problem["signature"], None)
    header = shebang + "\n" + f'"""{problem["statement"]}"""\n\n\n'
    if isinstance(signature, dict) and "methods" in signature:
        lines = [
            f"class {problem['function_name']}:",
            "    def __init__(self):",
            f"        {TEMPLATE_STUB_COMMENT}",
            "        raise NotImplementedError",
        ]
        for name, sig in signature["methods"].items():
            lines += [
                "",
                f"    def {name}{sig}:",
                f"        {TEMPLATE_STUB_COMMENT}",
                "        raise NotImplementedError",
            ]
        return header + "\n".join(lines) + "\n"
    if isinstance(signature, dict) and "functions" in signature:
        parts = []
        for name, sig in signature["functions"].items():
            parts.append(
                f"def {name}{sig}:\n    {TEMPLATE_STUB_COMMENT}\n"
                "    raise NotImplementedError"
            )
        return header + "\n\n".join(parts) + "\n"
    return (
        header
        + f"def {problem['function_name']}{signature or ''}:\n"
        f"    {TEMPLATE_STUB_COMMENT}\n    raise NotImplementedError\n"
    )


def _get_problem(conn: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM problems WHERE slug = ?", (slug,)).fetchone()


def _build_cases(problem: sqlite3.Row, rng: random.Random) -> list[dict]:
    cases = [
        {**c, "label": f"visible {i + 1}"}
        for i, c in enumerate(loads_json(problem["visible_tests"], []) or [])
    ]
    generator = JUDGE_CASES.get(problem["slug"])
    if generator:
        for i in range(GENERATED_CASES):
            n = rng.randint(0, 12)
            generated = generator(n, rng)
            args, expected = generated[:2]
            extras = generated[2] if len(generated) > 2 else {}
            cases.append(
                {
                    "args": args,
                    "expected": expected,
                    "label": f"generated {i + 1}",
                    **extras,
                }
            )
    return cases


def _show_case_failures(console: Console, report) -> None:
    table = ui_table("Failed cases")
    table.add_column("Case")
    table.add_column("Expected")
    table.add_column("Got")
    table.add_column("Error")
    for r in report.results:
        if r.passed:
            continue
        table.add_row(
            r.label,
            _truncate(str(r.expected)),
            _truncate(str(r.got)),
            (r.error or "")[:60],
        )
    console.print(table)


def _truncate(text: str, limit: int = 60) -> str:
    """Truncate with an ellipsis — a hard cut mid-list reads as malformed
    data (it once convinced a student the expected value was corrupt)."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _axis_outcomes(
    expected: str | None,
    claimed: str | None,
    measured: "FitResult | None",
) -> dict[str, str]:
    """The three pairwise comparisons of one axis. The measured side carries
    its bracket, so a claim the measurement cannot rule out is not a
    disagreement."""
    bracket = measured.bracket if measured is not None else None
    measured_class = measured.best_class if measured is not None else None
    return {
        "claim_vs_expected": complexity.compare(claimed, expected),
        "measured_vs_claimed": complexity.compare(measured_class, claimed, b_bracket=bracket),
        "measured_vs_expected": complexity.compare(measured_class, expected, b_bracket=bracket),
    }


def _show_complexity_table(
    console: Console,
    expected_time: str | None,
    expected_space: str | None,
    claimed_time: str | None,
    claimed_space: str | None,
    time_fit: "FitResult | None",
    space_fit: "FitResult | None",
) -> None:
    """The three-way table. Red means *disagreement*; an axis whose sides are
    not comparable (a multi-parameter claim against a single-parameter
    measurement) is marked as such instead of being silently skipped, and a
    bracketed measurement never reddens a claim it contains (v0.11)."""
    table = ui_table("Complexity: expected vs. claimed vs. measured")
    table.add_column("")
    table.add_column("Expected")
    table.add_column("You claimed")
    table.add_column("Measured")
    table.add_column("R²")
    notes: list[str] = []
    ambiguous: list[str] = []

    def axis_cells(
        axis: str,
        expected: str | None,
        claimed: str | None,
        fit: "FitResult | None",
    ) -> tuple:
        outcomes = _axis_outcomes(expected, claimed, fit)
        measured_label = fit.label if fit is not None else None
        disagree = {k for k, v in outcomes.items() if v == complexity.DISAGREE}
        incomparable = {k for k, v in outcomes.items() if v == complexity.INCOMPARABLE}
        for key in ("claim_vs_expected", "measured_vs_claimed", "measured_vs_expected"):
            if key in disagree:
                notes.append(f"{axis}: {key.replace('_', ' ')}")
        if incomparable and expected and claimed and fit is not None:
            ambiguous.append(
                f"{axis}: the measurement scales a single size parameter, so it "
                "does not speak to a claim in other variables"
            )
        if fit is not None and fit.bracket:
            ambiguous.append(f"{axis}: {fit.note}")
        agree_all = (
            not disagree
            and not incomparable
            and all(v is not None for v in (expected, claimed, measured_label))
            and all(outcome == complexity.AGREE for outcome in outcomes.values())
        )

        def cell(value: str | None, red: bool) -> Text | str:
            text = value or "—"
            if red:
                return Text(text, style="red")
            if agree_all:
                return Text(text, style="green")
            return text

        return (
            cell(expected, "claim_vs_expected" in disagree or "measured_vs_expected" in disagree),
            cell(claimed, "claim_vs_expected" in disagree or "measured_vs_claimed" in disagree),
            cell(measured_label, "measured_vs_claimed" in disagree or "measured_vs_expected" in disagree),
        )

    expected_cell, claimed_cell, measured_cell = axis_cells(
        "time", expected_time, claimed_time, time_fit
    )
    table.add_row(
        "Time", expected_cell, claimed_cell, measured_cell,
        "—" if time_fit is None or time_fit.r2 is None else str(time_fit.r2),
    )
    expected_cell, claimed_cell, measured_cell = axis_cells(
        "space", expected_space, claimed_space, space_fit
    )
    table.add_row(
        "Space", expected_cell, claimed_cell, measured_cell,
        "—" if space_fit is None or space_fit.r2 is None else str(space_fit.r2),
    )
    console.print(table)
    if notes:
        console.print(
            "[yellow]Red cells disagree (evidence, not verdicts) — investigate "
            "whether it's the algorithm, the claim, or measurement noise "
            "(low R² leans noise).[/yellow]"
        )
    for line in dict.fromkeys(ambiguous):
        console.print(f"[dim]{line}[/dim]")


def _measurement_note(fit: "FitResult | None") -> str | None:
    """What the reviewer needs to know about a measurement's strength — it
    used to be handed a bare class and left to guess whether a disagreement
    was evidence or an artifact."""
    if fit is None:
        return None
    if fit.bracket:
        return (
            f"ambiguous at this noise level (R²={fit.r2}); the data cannot "
            f"separate {' from '.join(fit.bracket)} — not evidence against the claim"
        )
    if not fit.confident:
        return f"low confidence (R²={fit.r2}); treat as suggestive, not a verdict"
    return f"R²={fit.r2}"


def _write_template(problem: sqlite3.Row, force: bool = False) -> None:
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKBENCH_DIR / f"{problem['slug']}.py"
    if path.exists() and not force:
        return
    path.write_text(_render_template(problem))


def _show_printed(console: Console, report) -> None:
    """The captured stdout of the user's code (v0.10.7): prints are
    debugging statements, and `check` is the debugging loop."""
    printed_cases = [(r.label, r.printed) for r in report.results if r.printed]
    if not printed_cases:
        return
    console.print("[bold]Your code printed:[/bold]")
    for label, text in printed_cases:
        console.print(f"[dim]{label}:[/dim]")
        console.print(text.rstrip())


def _check(console: Console, problem: sqlite3.Row, code_path: Path) -> bool:
    cases = [
        {**c, "label": f"visible {i + 1}"}
        for i, c in enumerate(loads_json(problem["visible_tests"], []) or [])
    ]
    report = run_cases(code_path, problem["function_name"], cases)
    if report.all_passed:
        console.print(f"[green]✓ {report.passed}/{report.total} visible cases passed[/green]")
    else:
        _show_case_failures(console, report)
    _show_printed(console, report)
    # Advisory static analysis: findings here are live coaching, so the
    # student can fix them before the reviewer grades the final code.
    analysis = static.analyze(code_path)
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)
    return report.all_passed


def _measure_complexity(
    console: Console, problem: sqlite3.Row, code_path: Path
) -> tuple["FitResult | None", "FitResult | None"]:
    """Empirical measurement, shared by submit and polish. Returns the time
    and space fits — each carrying the class *and* the bracket the data
    cannot resolve past."""
    time_fit = space_fit = None
    if problem["slug"] in PROFILER_INPUTS:
        console.print("[bold]Measuring empirical complexity[/bold] (doubling input sizes, median of repeats)...")
        m = measure(
            code_path,
            problem["function_name"],
            PROFILER_INPUTS[problem["slug"]],
        )
        if m.time_points:
            time_fit = classify(
                [n for n, _ in m.time_points],
                [t for _, t in m.time_points],
                spread=m.spread,
            )
        if m.space_points:
            # Space fits on every-second point: container allocations are a
            # power-of-two staircase, and exact-doubling sampling aliases a
            # linear structure as O(n^2) (see fit.staircase_safe_points).
            safe = staircase_safe_points(m.space_points)
            space_fit = classify(
                [n for n, _ in safe], [s for _, s in safe], spread=m.spread
            )
        if m.dropped:
            console.print(f"[dim](dropped sizes: {', '.join(m.dropped)})[/dim]")
    else:
        console.print("[dim]No profiler input generator registered for this problem — skipping measurement.[/dim]")
    return time_fit, space_fit


def _ask_question(console: Console, label: str, default: str | None = None) -> str:
    """A styled question with breathing room: the question line (bold
    cyan), then the answer typed on its own line. ``default`` prefills
    the previous answer when editing (TTY only)."""
    console.print()
    console.print(f"[bold cyan]{label}[/bold cyan]")
    return make_prompt(console)("[dim]  ❯[/dim] ", default=default).strip()


def _ask_complexity_claims(
    console: Console,
    time_default: str | None = None,
    space_default: str | None = None,
) -> tuple[str, str]:
    """The two complexity questions + the double-check gate (v0.9.1),
    shared by submit and polish. Polish passes the previous claims as
    prefilled defaults — the edited code may be a different algorithm, so
    the claims are re-collected instead of silently reused (v0.9.3)."""
    prompt = make_prompt(console)
    claimed_time_raw = _ask_question(
        console, "State your time complexity and why:", default=time_default
    )
    claimed_space_raw = _ask_question(
        console, "State your space complexity and why:", default=space_default
    )
    while True:
        # The double-check gate: two separate questions, one chance to fix
        # either before the machine measures — `time`/`space` re-asks that
        # one (prefilled), Enter continues.
        console.print()
        console.print("[bold cyan]Double-check before measuring:[/bold cyan]")
        console.print(f"  [cyan]time:[/cyan]  {claimed_time_raw or '—'}")
        console.print(f"  [cyan]space:[/cyan] {claimed_space_raw or '—'}")
        edit = prompt(
            "[dim]Enter to continue · `time` or `space` to edit: [/dim]"
        ).strip().lower()
        if edit in ("", "ok", "y", "yes"):
            break
        if edit in ("time", "t"):
            claimed_time_raw = _ask_question(
                console, "State your time complexity and why:", default=claimed_time_raw
            )
        elif edit in ("space", "s"):
            claimed_space_raw = _ask_question(
                console,
                "State your space complexity and why:",
                default=claimed_space_raw,
            )
        else:
            console.print("[dim]`time`, `space`, or Enter.[/dim]")
    return claimed_time_raw, claimed_space_raw


def _record_submit(
    conn: sqlite3.Connection,
    state: WorkbenchState,
    problem: sqlite3.Row,
    user_id: int,
    report,
) -> int:
    """Create this session's attempt row on the first submit, update it on
    every later one (v0.11: **an attempt exists iff the student submitted**).

    The judge's own verdict is the status, so a failed submit is a real
    attempt and `status` carries information — instead of the placeholder
    'unsolved' that merely starting a session used to write."""
    code = state.code_path.read_text()
    submitted_at = now()
    if state.attempt_id is None:
        cur = conn.execute(
            """
            INSERT INTO attempts
                (user_id, problem_id, kind, status, code, started_at, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                problem["id"],
                state.kind,
                report.status,
                code,
                iso_from_epoch(state.started_epoch),
                submitted_at,
            ),
        )
        conn.commit()
        return cur.lastrowid
    conn.execute(
        "UPDATE attempts SET status = ?, code = ?, submitted_at = ? WHERE id = ?",
        (report.status, code, submitted_at, state.attempt_id),
    )
    conn.commit()
    return state.attempt_id


def _submit(
    conn: sqlite3.Connection,
    console: Console,
    backend,
    problem: sqlite3.Row,
    state: WorkbenchState,
    user_id: int,
    warmup: bool = False,
) -> tuple[str, str | None]:
    """Run the full pipeline on the current code. Returns
    ("keep_going", None) on failed cases, ("solved", reflection) on success.
    Warm-ups skip the reflection prompt — the recall grade replaces it.

    The attempt row is created by this call (v0.11): a session that never
    submits never records anything."""
    code_path = state.code_path
    rng = random.Random(f"dojo-{problem['slug']}")
    cases = _build_cases(problem, rng)
    console.print(f"[bold]Judging {len(cases)} cases[/bold] (visible + generated + oracle-checked)...")
    report = run_cases(code_path, problem["function_name"], cases)
    state.attempt_id = _record_submit(conn, state, problem, user_id, report)
    save_state(state)
    if not report.all_passed:
        console.print(
            f"[red]✗ {report.passed}/{report.total} passed[/red]"
            + (f" — status: {report.status}" if report.status != "wrong_answer" else "")
        )
        _show_case_failures(console, report)
        _show_printed(console, report)
        return "keep_going", None

    console.print(f"[green]✓ All {report.total} cases passed[/green]")

    analysis = static.analyze(code_path)
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)

    claimed_time_raw, claimed_space_raw = _ask_complexity_claims(console)
    claimed_time = complexity.parse(claimed_time_raw)
    claimed_space = complexity.parse(claimed_space_raw)

    time_fit, space_fit = _measure_complexity(console, problem, code_path)

    _show_complexity_table(
        console,
        problem["expected_time"],
        problem["expected_space"],
        claimed_time,
        claimed_space,
        time_fit,
        space_fit,
    )

    # Reflect first, so the reviewer can comment on the reflection.
    reflection = None
    if not warmup:
        reflection = _ask_question(
            console,
            "Reflection — what was the key insight, and when would you reach "
            "for this again?",
        )

    console.print("[bold]AI review[/bold] (post-submission; the reviewer critiques, it never repairs)...")
    code = code_path.read_text()
    review_json = review(
        backend,
        problem["statement"],
        code,
        claimed_time_raw,
        claimed_space_raw,
        time_fit.label if time_fit else None,
        space_fit.label if space_fit else None,
        problem["expected_time"],
        problem["expected_space"],
        static_analysis=analysis,
        reflection=reflection,
        measured_time_note=_measurement_note(time_fit),
        measured_space_note=_measurement_note(space_fit),
    )
    if "error" in review_json:
        console.print("[yellow]Reviewer unavailable (non-JSON response) — review skipped.[/yellow]")
        review_json = {}
    else:
        _show_review(console, review_json)

    conn.execute(
        """
        UPDATE attempts SET
            code = ?, status = 'correct', submitted_at = ?,
            duration_seconds = ?,
            hint_count = ?, hints = ?,
            self_reported_time = ?, self_reported_space = ?,
            measured_time_class = ?, measured_time_r2 = ?,
            measured_space_class = ?, measured_space_r2 = ?,
            review = ?, reflection = ?, static_analysis = ?
        WHERE id = ?
        """,
        (
            code,
            now(),
            round(time.time() - state.started_epoch, 1),
            len(state.hints),
            dumps_json(state.hints),
            claimed_time_raw,
            claimed_space_raw,
            time_fit.label if time_fit else None,
            time_fit.r2 if time_fit else None,
            space_fit.label if space_fit else None,
            space_fit.r2 if space_fit else None,
            dumps_json(review_json) if review_json else None,
            reflection,
            dumps_json(analysis.to_dict()),
            state.attempt_id,
        ),
    )
    conn.commit()
    console.print(
        Panel(
            f"[bold green]Solved:[/bold green] {problem['title']} — attempt recorded.\n"
            f"Claimed: {claimed_time or '?'} / {claimed_space or '?'}  ·  "
            f"Measured: {(time_fit.label if time_fit else None) or '—'} / "
            f"{(space_fit.label if space_fit else None) or '—'}  ·  "
            f"Hints used: {len(state.hints)}",
            title="Session complete",
        )
    )
    return "solved", reflection


def _show_static(console: Console, analysis) -> None:
    console.print("[bold]Static analysis[/bold] (radon + ruff)...")
    for flag in analysis.flags:
        console.print(f"[yellow]• {flag}[/yellow]")
    for note in analysis.notes:
        console.print(f"[dim]• {note}[/dim]")


def _show_review(console: Console, review_json: dict) -> None:
    """The rubric as one markdown panel (v0.10.11): headings carry the
    scores, comments keep their markdown — no table column to flatten
    them into."""
    render_ai(
        console, "AI review", review_markdown(review_json), border_style="green"
    )


def _polish(conn: sqlite3.Connection, console: Console, backend, problem: sqlite3.Row, state: WorkbenchState) -> None:
    """Post-solve re-grade: re-judge, re-measure, re-analyze the edited code
    and update the same attempt row (polished counter bumps). Complexity
    claims are re-collected with the previous answers prefilled — the
    edited code may be a different algorithm, and comparing a new
    measurement against stale claims produced spurious flags (v0.9.3)."""
    code_path = state.code_path
    rng = random.Random(f"dojo-{problem['slug']}")
    cases = _build_cases(problem, rng)
    report = run_cases(code_path, problem["function_name"], cases)
    if not report.all_passed:
        console.print(f"[red]✗ {report.passed}/{report.total} passed[/red]")
        _show_case_failures(console, report)
        return
    console.print(f"[green]✓ All {report.total} cases passed[/green]")

    row = conn.execute(
        "SELECT self_reported_time, self_reported_space, review FROM attempts WHERE id = ?",
        (state.attempt_id,),
    ).fetchone()
    analysis = static.analyze(code_path)
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)
    # Re-collect the claims for the *edited* code (v0.9.3): comparing a new
    # measurement against the original claims produced spurious flags. The
    # previous answers prefill, so an unchanged polish costs three Enters.
    claimed_time_raw, claimed_space_raw = _ask_complexity_claims(
        console,
        time_default=row["self_reported_time"],
        space_default=row["self_reported_space"],
    )
    claimed_time = complexity.parse(claimed_time_raw)
    claimed_space = complexity.parse(claimed_space_raw)
    time_fit, space_fit = _measure_complexity(console, problem, code_path)
    _show_complexity_table(
        console,
        problem["expected_time"],
        problem["expected_space"],
        claimed_time,
        claimed_space,
        time_fit,
        space_fit,
    )

    review_json = loads_json(row["review"], {})
    if make_prompt(console)("Review again? [y/N]: ").strip().lower() in ("y", "yes"):
        review_json = review(
            backend,
            problem["statement"],
            code_path.read_text(),
            claimed_time_raw,
            claimed_space_raw,
            time_fit.label if time_fit else None,
            space_fit.label if space_fit else None,
            problem["expected_time"],
            problem["expected_space"],
            static_analysis=analysis,
            measured_time_note=_measurement_note(time_fit),
            measured_space_note=_measurement_note(space_fit),
        )
        if "error" in review_json:
            console.print("[yellow]Reviewer unavailable (non-JSON response) — review kept as-is.[/yellow]")
            review_json = {}
        else:
            _show_review(console, review_json)

    conn.execute(
        """
        UPDATE attempts SET
            code = ?, submitted_at = ?,
            self_reported_time = ?, self_reported_space = ?,
            measured_time_class = ?, measured_time_r2 = ?,
            measured_space_class = ?, measured_space_r2 = ?,
            static_analysis = ?, review = ?, polished = polished + 1
        WHERE id = ?
        """,
        (
            code_path.read_text(),
            now(),
            claimed_time_raw,
            claimed_space_raw,
            time_fit.label if time_fit else None,
            time_fit.r2 if time_fit else None,
            space_fit.label if space_fit else None,
            space_fit.r2 if space_fit else None,
            dumps_json(analysis.to_dict()),
            dumps_json(review_json) if review_json else None,
            state.attempt_id,
        ),
    )
    conn.commit()
    console.print("[green]Polished — attempt updated.[/green]")


def _discuss(conn: sqlite3.Connection, console: Console, backend, problem: sqlite3.Row, state: WorkbenchState, question: str) -> None:
    """Post-solve chat: the never-solve boundary lifts, the transcript
    persists on the attempt row. The prompt carries the submitted code so
    the model grounds on what actually ran (v0.8.1)."""
    history = loads_json(
        conn.execute(
            "SELECT discussion FROM attempts WHERE id = ?", (state.attempt_id,)
        ).fetchone()["discussion"],
        [],
    )
    prompt = build_discussion_prompt(
        problem["statement"], state.code_path.read_text(), history, question
    )
    answer = backend.chat(DISCUSSION_SYSTEM, prompt)  # raw markdown (v0.10.3)
    render_ai(console, "tutor — post-solve discussion", answer, border_style="green")
    conn.execute(
        "UPDATE attempts SET discussion = ? WHERE id = ?",
        (dumps_json(history + [{"user": question, "tutor": answer}]), state.attempt_id),
    )
    conn.commit()


def _post_solve_loop(conn: sqlite3.Connection, console: Console, backend, problem: sqlite3.Row, state: WorkbenchState) -> None:
    """After review + reflection: polish (re-grade edits), done (retire) —
    and any other input is a discussion question (v0.10.1: the `discuss`
    command is gone; bare questions reach the tutor here too)."""
    prompt = make_prompt(console)
    while True:
        raw = prompt(
            "[bold cyan]dojo ›[/bold cyan] ",
            hint=f"[dim]{POST_COMMANDS_HINT}[/dim]",
        ).strip()
        if not raw:
            continue
        fixed = confirm_typo(console, raw, ["polish", "p", "done", "quit", "q"])
        if fixed is not None:
            raw = fixed
        if raw in ("done", "quit", "q"):
            return
        if raw in ("polish", "p"):
            _polish(conn, console, backend, problem, state)
        else:
            _discuss(conn, console, backend, problem, state, raw)


def _abandon(console: Console, state: WorkbenchState, message: str) -> None:
    """End a session with nothing recorded (v0.11). An attempt row exists iff
    the student submitted, so abandoning — a glance at the tool, a change of
    mind, a `learn` handoff — writes nothing to the learner model: no row, no
    hints, no code, no lapse. The state file is retired, so the next
    invocation starts fresh."""
    console.print(message)
    retire_state(state.slug)


def suggested_grade(hints: list[dict]) -> int:
    """A prior for the recall grade from the hints a session used (v0.11).

    Only ``ladder`` hints count: a ``discussion`` question is exploring, not
    struggling, and the old mapping counted every hint. The suggestion tops out
    at 3 — a hint-free re-solve is evidence *against* struggle, not evidence of
    ease, and FSRS's easy bonus multiplies the whole grown stability by 2.61,
    so claiming "easy" should be a deliberate choice rather than the default.
    Three or more ladder hints is a real lapse signal."""
    ladder = sum(1 for h in hints if h.get("kind") != "discussion")
    if not ladder:
        return 3
    if ladder <= 2:
        return 2
    return 1


def _ask_grade(console: Console, hints: list[dict]) -> int:
    suggested = suggested_grade(hints)
    raw = make_prompt(console)(
        f"Recall grade [4=easy 3=good 2=hard 1=forgot] (suggested {suggested}): "
    ).strip()
    try:
        grade = int(raw)
        if grade not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        grade = suggested
    return grade


def _show_card_update(
    console: Console, card: sqlite3.Row, summary: dict, lapse: bool
) -> None:
    console.print(
        Panel(
            f"pattern: [bold]{card['pattern']}[/bold]\n"
            f"stability: {card['stability']:.2f} → {summary['stability']:.2f} days\n"
            f"difficulty: {card['difficulty']:.1f} → {summary['difficulty']:.1f}\n"
            f"next warm-up: [bold]{scheduler.humanize_due(summary['due_at'])}[/bold]",
            title="Card updated — lapse" if lapse else "Card updated",
            border_style="red" if lapse else "green",
        )
    )
    if not lapse and card["last_reflection"]:
        console.print(
            Panel(
                card["last_reflection"],
                title="Your last reflection on this pattern",
                border_style="blue",
            )
        )


def run_day(
    conn: sqlite3.Connection,
    console: Console,
    backend,
    slug: str,
    user_name: str,
    open_editor: bool = False,
    warmup: bool = False,
    card: sqlite3.Row | None = None,
) -> str:
    # Prints between prompts route through patch_stdout on TTYs, so the
    # fullscreen prompt's repaint can't visually truncate them (v0.10.1).
    console = patch_console(console)
    problem = _get_problem(conn, slug)
    if problem is None:
        console.print(f"[red]Unknown problem '{slug}'. Try `dojo list`.[/red]")
        return "error"
    if not problem["function_name"] or not problem["visible_tests"]:
        console.print(
            f"[red]'{slug}' is not curated yet (missing function name or visible "
            "tests in data/problem_overrides.json).[/red]"
        )
        return "error"

    user_id = get_or_create_user(conn, user_name)
    kind = "warmup" if warmup else "solve"
    state = load_state(slug)
    is_new_session = state is None or state.user_id != user_id or state.kind != kind
    if is_new_session:
        # No attempt row yet (v0.11): submitting creates it. A new session is
        # only the state file and a blank template.
        state = WorkbenchState(
            slug=slug,
            user_id=user_id,
            started_epoch=time.time(),
            kind=kind,
        )
        save_state(state)

    # Every new session starts from a blank template — previous solutions
    # live on attempt rows (`dojo history` / `dojo show <id>`), not in the
    # workbench. A session that resumes existing state (crash recovery)
    # keeps whatever is in the file.
    _write_template(problem, force=is_new_session)
    # The workbench carries its own IDE workspace (v0.10.6): a generated
    # .vscode/ + code-workspace pointing at dojo's venv, so opening the
    # folder in VSCode debugs user code without knowing the repo exists.
    ensure_ide_config(WORKBENCH_DIR)
    if warmup:
        console.print(
            Panel(
                f"[bold]Warm-up[/bold] — re-solve [bold]{problem['title']}[/bold] "
                f"from scratch ([bold]{problem['pattern']}[/bold] pattern)\n\n"
                f"{problem['statement']}\n\n"
                f"Workbench: {state.code_path}",
                title="dojo",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold]{problem['title']}[/bold] [{problem['difficulty']}] — {problem['pattern']}\n\n"
                f"{problem['statement']}\n\n"
                f"Workbench: {state.code_path}",
                title="dojo",
            )
        )

    if open_editor:
        console.print(launch_editor(state.code_path))

    def do_hint(question: str) -> None:
        result = ask_tutor(
            backend,
            problem["statement"],
            state.code_path.read_text(),
            state.tier,
            question,
            state.hints,
        )
        if not result.delivered:
            console.print(
                "[yellow]Tutor couldn't answer without leaking the solution "
                "— try rephrasing.[/yellow]"
            )
            return
        state.hints.append(
            {
                "kind": result.kind,
                "tier": result.tier,
                "user": question,
                "hint": result.text,  # raw markdown (v0.10.3); rendered at display
            }
        )
        if result.kind == "ladder":
            state.tier = min(result.tier + 1, 5)
        save_state(state)
        if result.kind == "ladder":
            render_ai(
                console,
                f"tutor · tier {result.tier} — {TIER_NAMES[result.tier]}",
                result.text,
                border_style="blue",
            )
            console.print(
                f"[dim]Next hint will be tier {state.tier} ({TIER_NAMES[state.tier]}).[/dim]"
            )
        else:
            render_ai(console, "tutor", result.text, border_style="blue")

    prompt = make_prompt(console)
    while True:
        raw = prompt(
            "[bold cyan]dojo ›[/bold cyan] ",
            hint=f"[dim]{COMMANDS_HINT}[/dim]",
        ).strip()
        if not raw:
            continue
        cmd, _, rest = raw.partition(" ")
        fixed = confirm_typo(
            console, cmd, ["open", "check", "learn", "submit", "quit", "q", "report"]
        )
        if fixed is not None:
            raw = fixed
            cmd, _, rest = fixed.partition(" ")
        if cmd in ("q", "quit") and not rest:
            _abandon(
                console,
                state,
                "[dim]Session abandoned — nothing recorded. Next session "
                "starts fresh.[/dim]",
            )
            return "quit"
        if cmd in ("c", "check") and not rest:
            _check(console, problem, state.code_path)
        elif cmd in ("o", "open") and not rest:
            console.print(launch_editor(state.code_path))
        elif cmd in ("l", "learn"):
            if warmup:
                console.print(
                    "[dim]Learn mode isn't available during a warm-up — a "
                    "warm-up is a graded recall, so leaving it records a "
                    "lapse. Finish or quit it, then `dojo learn`.[/dim]"
                )
                continue
            if rest.strip():
                pattern, suggestion = resolve_pattern(rest.strip())
                if pattern is None:
                    if suggestion:
                        console.print(
                            f"[yellow]Unknown pattern '{rest.strip()}' — did you "
                            f"mean '{suggestion}'?[/yellow]"
                        )
                    else:
                        console.print(f"[red]Unknown pattern '{rest.strip()}'.[/red]")
                    continue
            else:
                pattern = problem["pattern"]
                if not pattern:
                    console.print(
                        "[yellow]This problem has no pattern — try "
                        "`learn <topic>` instead.[/yellow]"
                    )
                    continue
            _abandon(
                console,
                state,
                "[dim]Abandoned for study — nothing recorded; the learn "
                "session can hand you back to this problem fresh.[/dim]",
            )
            result = run_learn(
                conn, console, backend, user_name, pattern, handoff_slug=state.slug
            )
            return "practice" if result.get("practice") else "quit"
        elif cmd in ("r", "report") and not rest:
            try:
                from dojo.curator import CuratorError, audit_curation

                audit = audit_curation(
                    backend,
                    problem["statement"],
                    loads_json(problem["visible_tests"], []),
                    live_oracle=ORACLES.get(problem["slug"]),
                    live_generator=JUDGE_CASES.get(problem["slug"]),
                )
                console.print(
                    f"[bold]Curation audit[/bold] — verdict: {audit.get('verdict', '?')}"
                )
                for finding in audit.get("findings") or []:
                    console.print(f"[yellow]• {finding}[/yellow]")
                if not (audit.get("findings") or []):
                    console.print("[green]No contract violations found.[/green]")
                console.print(
                    "[dim]`dojo report --fix <slug>` re-curates when the verdict is 'fix'.[/dim]"
                )
            except CuratorError as exc:
                console.print(f"[red]Audit failed: {exc}[/red]")
        elif cmd in ("s", "submit") and not rest:
            outcome, reflection = _submit(
                conn, console, backend, problem, state, user_id, warmup=warmup
            )
            if outcome == "solved":
                if warmup and card is not None:
                    grade = _ask_grade(console, state.hints)
                    summary = scheduler.record_grade(conn, card, grade)
                    # The grade itself is the retention model's one input —
                    # persist it instead of keeping only the card aggregates.
                    conn.execute(
                        "UPDATE attempts SET recall_grade = ? WHERE id = ?",
                        (grade, state.attempt_id),
                    )
                    conn.commit()
                    _show_card_update(console, card, summary, lapse=(grade == 1))
                    retire_state(state.slug)
                    return "warmup_done"
                # A first solve carries evidence about the pattern in its own
                # hint count — seed the card with it rather than a flat default.
                scheduler.ensure_card(
                    conn,
                    user_id,
                    problem["pattern"],
                    reflection=reflection,
                    grade=suggested_grade(state.hints),
                )
                if not warmup:
                    _post_solve_loop(conn, console, backend, problem, state)
                retire_state(state.slug)
                return "solved"
        else:
            # Bare questions — and command words with extra text ("check my
            # solution...") — are hints, never "Unknown command" (v0.10.1:
            # the `hint` command itself is gone; a leading "hint " prefix is
            # still stripped for muscle memory).
            question = raw
            if raw.lower() in ("h", "hint"):
                question = "I'm stuck"
            elif raw.lower().startswith("hint "):
                question = raw[5:].strip()
            do_hint(question)


def run_warmups(
    conn: sqlite3.Connection,
    console: Console,
    backend,
    user_name: str,
    limit: int = 2,
) -> list[str]:
    """Run due warm-up retrievals (re-solve solved problems from scratch),
    most overdue first. Stops early if the student quits a warm-up."""
    user_id = get_or_create_user(conn, user_name)
    cards = scheduler.due_cards(conn, user_id, limit=limit)
    if not cards:
        console.print("[green]No warm-ups due — the scheduler says you're fresh.[/green]")
        return []
    console.print(f"[bold]Warm-up: {len(cards)} pattern card(s) due.[/bold]")
    outcomes = []
    for card in cards:
        problem = scheduler.warmup_problem(conn, user_id, card["pattern"])
        if problem is None:
            console.print(
                f"[yellow]Card '{card['pattern']}' has no solved problem to "
                "re-solve; deferring it a day.[/yellow]"
            )
            scheduler.defer(conn, card, days=1.0)
            continue
        _write_template(problem, force=True)
        outcome = run_day(
            conn, console, backend, problem["slug"], user_name,
            open_editor=False, warmup=True, card=card,
        )
        outcomes.append(outcome)
        if outcome in ("quit", "practice"):
            break
    return outcomes


def run_check(conn: sqlite3.Connection, console: Console, slug: str) -> str:
    problem = _get_problem(conn, slug)
    if problem is None:
        console.print(f"[red]Unknown problem '{slug}'.[/red]")
        return "error"
    state = load_state(slug)
    if state is None or not state.code_path.exists():
        console.print(f"[red]No active session for '{slug}'. Start one with `dojo day {slug}`.[/red]")
        return "error"
    _check(console, problem, state.code_path)
    return "ok"
