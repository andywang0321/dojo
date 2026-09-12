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
from rich.table import Table
from rich.text import Text

from dojo import complexity, scheduler, static
from dojo.config import VENV_PYTHON, WORKBENCH_DIR
from dojo.db import dumps_json, get_or_create_user, loads_json, now
from dojo.editor import ensure_ide_config, launch as launch_editor
from dojo.judge import JUDGE_CASES, ORACLES, PROFILER_INPUTS, run_cases
from dojo.profiler import classify, measure, staircase_safe_points
from dojo.render import md_plain, render_ai
from dojo.session.learn import resolve_pattern, run_learn
from dojo.session.state import (
    WorkbenchState,
    load_state,
    retire_state,
    save_state,
)
from dojo.terminal import make_prompt, patch_console
from dojo.tutor import TIER_NAMES, ask_tutor, review
from dojo.tutor.prompts import DISCUSSION_SYSTEM, build_discussion_prompt
from dojo.ui import table as ui_table

GENERATED_CASES = 30

COMMANDS_HINT = "open · check · learn · submit · quit — or ask"

POST_COMMANDS_HINT = "polish · done — or ask"

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


def _show_complexity_table(
    console: Console,
    expected_time: str | None,
    expected_space: str | None,
    claimed_time: str | None,
    claimed_space: str | None,
    measured_time: str | None,
    measured_space: str | None,
    time_r2: float | None = None,
    space_r2: float | None = None,
) -> None:
    table = ui_table("Complexity: expected vs. claimed vs. measured")
    table.add_column("")
    table.add_column("Expected")
    table.add_column("You claimed")
    table.add_column("Measured")
    table.add_column("R²")
    notes = []
    if complexity.mismatch(claimed_time, expected_time):
        notes.append("time: claim vs expected")
    if complexity.mismatch(claimed_time, measured_time):
        notes.append("time: claim vs measurement")
    if complexity.mismatch(expected_time, measured_time):
        notes.append("time: expected vs measurement")
    if complexity.mismatch(claimed_space, expected_space):
        notes.append("space: claim vs expected")
    if complexity.mismatch(claimed_space, measured_space):
        notes.append("space: claim vs measurement")
    if complexity.mismatch(expected_space, measured_space):
        notes.append("space: expected vs measurement")

    def r2_cell(measured: str | None, r2: float | None) -> str:
        return "—" if measured is None or r2 is None else str(r2)

    def axis_cells(
        expected: str | None, claimed: str | None, measured: str | None
    ) -> tuple:
        """Color-code the three cells of one axis: any cell participating in
        a mismatch goes red; when all three agree, they go green. Cells
        untouched by a mismatch stay neutral. Cell values are rendered as
        literal `Text` — rich Tables strip markup in cells."""
        claimed_vs_expected = complexity.mismatch(claimed, expected)
        measured_vs_claimed = complexity.mismatch(measured, claimed)
        measured_vs_expected = complexity.mismatch(measured, expected)
        any_mismatch = claimed_vs_expected or measured_vs_claimed or measured_vs_expected
        all_agree = (
            not any_mismatch
            and all(v is not None for v in (expected, claimed, measured))
            and expected == claimed == measured
        )

        def cell(value: str | None, red: bool) -> Text | str:
            text = value or "-"
            if red:
                return Text(text, style="red")
            if all_agree:
                return Text(text, style="green")
            return text

        return (
            cell(expected, claimed_vs_expected or measured_vs_expected),
            cell(claimed, claimed_vs_expected or measured_vs_claimed),
            cell(measured, measured_vs_claimed or measured_vs_expected),
        )

    expected_cell, claimed_cell, measured_cell = axis_cells(
        expected_time, claimed_time, measured_time
    )
    table.add_row(
        "Time",
        expected_cell,
        claimed_cell,
        measured_cell,
        r2_cell(measured_time, time_r2),
    )
    expected_cell, claimed_cell, measured_cell = axis_cells(
        expected_space, claimed_space, measured_space
    )
    table.add_row(
        "Space",
        expected_cell,
        claimed_cell,
        measured_cell,
        r2_cell(measured_space, space_r2),
    )
    console.print(table)
    if notes:
        console.print(
            "[yellow]Red cells disagree (evidence, not verdicts) — investigate "
            "whether it's the algorithm, the claim, or measurement noise "
            "(low R² leans noise).[/yellow]"
        )


def _write_template(problem: sqlite3.Row, force: bool = False) -> None:
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKBENCH_DIR / f"{problem['slug']}.py"
    if path.exists() and not force:
        return
    path.write_text(_render_template(problem))


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
    # Advisory static analysis: findings here are live coaching, so the
    # student can fix them before the reviewer grades the final code.
    analysis = static.analyze(code_path)
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)
    return report.all_passed


def _measure_complexity(
    console: Console, problem: sqlite3.Row, code_path: Path
) -> tuple[str | None, float | None, str | None, float | None]:
    """Empirical measurement + the three-way table (shared by submit and
    polish). Returns (measured_time, time_r2, measured_space, space_r2)."""
    measured_time = measured_space = time_r2 = space_r2 = None
    if problem["slug"] in PROFILER_INPUTS:
        console.print("[bold]Measuring empirical complexity[/bold] (doubling input sizes, median of repeats)...")
        m = measure(
            code_path,
            problem["function_name"],
            PROFILER_INPUTS[problem["slug"]],
        )
        if m.time_points:
            fit = classify([n for n, _ in m.time_points], [t for _, t in m.time_points])
            measured_time, time_r2 = fit.best_class, round(fit.r2, 3)
        if m.space_points:
            # Space fits on every-second point: container allocations are a
            # power-of-two staircase, and exact-doubling sampling aliases a
            # linear structure as O(n^2) (see fit.staircase_safe_points).
            safe = staircase_safe_points(m.space_points)
            sfit = classify([n for n, _ in safe], [s for _, s in safe])
            measured_space, space_r2 = sfit.best_class, round(sfit.r2, 3)
        if m.dropped:
            console.print(f"[dim](dropped sizes: {', '.join(m.dropped)})[/dim]")
    else:
        console.print("[dim]No profiler input generator registered for this problem — skipping measurement.[/dim]")
    return measured_time, time_r2, measured_space, space_r2


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


def _submit(
    conn: sqlite3.Connection,
    console: Console,
    backend,
    problem: sqlite3.Row,
    state: WorkbenchState,
    warmup: bool = False,
) -> tuple[str, str | None]:
    """Run the full pipeline on the current code. Returns
    ("keep_going", None) on failed cases, ("solved", reflection) on success.
    Warm-ups skip the reflection prompt — the recall grade replaces it."""
    code_path = state.code_path
    rng = random.Random(f"dojo-{problem['slug']}")
    cases = _build_cases(problem, rng)
    console.print(f"[bold]Judging {len(cases)} cases[/bold] (visible + generated + oracle-checked)...")
    report = run_cases(code_path, problem["function_name"], cases)
    if not report.all_passed:
        console.print(
            f"[red]✗ {report.passed}/{report.total} passed[/red]"
            + (f" — status: {report.status}" if report.status != "wrong_answer" else "")
        )
        _show_case_failures(console, report)
        return "keep_going", None

    console.print(f"[green]✓ All {report.total} cases passed[/green]")

    analysis = static.analyze(code_path)
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)

    claimed_time_raw, claimed_space_raw = _ask_complexity_claims(console)
    claimed_time = complexity.parse(claimed_time_raw)
    claimed_space = complexity.parse(claimed_space_raw)

    measured_time, time_r2, measured_space, space_r2 = _measure_complexity(
        console, problem, code_path
    )

    _show_complexity_table(
        console,
        problem["expected_time"],
        problem["expected_space"],
        claimed_time,
        claimed_space,
        measured_time,
        measured_space,
        time_r2,
        space_r2,
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
        measured_time,
        measured_space,
        problem["expected_time"],
        problem["expected_space"],
        static_analysis=analysis,
        reflection=reflection,
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
            measured_time,
            time_r2,
            measured_space,
            space_r2,
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
            f"Measured: {measured_time or '—'} / {measured_space or '—'}  ·  "
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
    table = ui_table("AI review")
    table.add_column("Dimension")
    table.add_column("Score")
    table.add_column("Comment")
    dims = [
        "correctness",
        "approach_quality",
        "style_idiom",
        "naming",
        "edge_cases",
        "complexity_claim_check",
        "complexity_reasoning",
    ]
    for dim in dims:
        entry = review_json.get(dim, {})
        if isinstance(entry, dict):
            table.add_row(
                dim.replace("_", " "),
                str(entry.get("score", "?")),
                md_plain(str(entry.get("comment", ""))),
            )
    console.print(table)
    if review_json.get("reflection_feedback"):
        render_ai(
            console,
            "On your reflection",
            str(review_json["reflection_feedback"]),
            border_style="cyan",
        )
    if review_json.get("broader_picture"):
        render_ai(console, "Broader picture", str(review_json["broader_picture"]))
    if review_json.get("overall_comment"):
        render_ai(console, "Overall", str(review_json["overall_comment"]))


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
    measured_time, time_r2, measured_space, space_r2 = _measure_complexity(
        console, problem, code_path
    )
    _show_complexity_table(
        console,
        problem["expected_time"],
        problem["expected_space"],
        claimed_time,
        claimed_space,
        measured_time,
        measured_space,
        time_r2,
        space_r2,
    )

    review_json = loads_json(row["review"], {})
    if make_prompt(console)("Review again? [y/N]: ").strip().lower() in ("y", "yes"):
        review_json = review(
            backend,
            problem["statement"],
            code_path.read_text(),
            claimed_time_raw,
            claimed_space_raw,
            measured_time,
            measured_space,
            problem["expected_time"],
            problem["expected_space"],
            static_analysis=analysis,
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
            measured_time,
            time_r2,
            measured_space,
            space_r2,
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
        if raw in ("done", "quit", "q"):
            return
        if raw in ("polish", "p"):
            _polish(conn, console, backend, problem, state)
        else:
            _discuss(conn, console, backend, problem, state, raw)


def _persist_abandoned(conn: sqlite3.Connection, state: WorkbenchState, console: Console, message: str) -> None:
    """The quit/learn parking persistence: code and hints land on the
    attempt row, status stays 'unsolved' — grading honesty is preserved
    because a later solve is a fresh attempt."""
    conn.execute(
        """
        UPDATE attempts SET
            code = ?, status = 'unsolved', hint_count = ?, hints = ?
        WHERE id = ?
        """,
        (
            state.code_path.read_text(),
            len(state.hints),
            dumps_json(state.hints),
            state.attempt_id,
        ),
    )
    conn.commit()
    console.print(message)


def _ask_grade(console: Console, hints: int) -> int:
    suggested = 4 if hints == 0 else 3 if hints == 1 else 2
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
        cur = conn.execute(
            "INSERT INTO attempts (user_id, problem_id, kind, status, started_at) "
            "VALUES (?, ?, ?, 'unsolved', ?)",
            (user_id, problem["id"], kind, now()),
        )
        conn.commit()
        state = WorkbenchState(
            slug=slug,
            attempt_id=cur.lastrowid,
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
        if cmd in ("q", "quit") and not rest:
            _persist_abandoned(
                conn,
                state,
                console,
                "[dim]Progress saved; attempt stays 'unsolved'. Next session "
                "starts fresh.[/dim]",
            )
            if warmup and card is not None:
                summary = scheduler.record_grade(conn, card, 1)
                _show_card_update(console, card, summary, lapse=True)
            retire_state(state.slug)
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
            _persist_abandoned(
                conn,
                state,
                console,
                "[dim]Paused for learning — progress saved; the attempt stays "
                "'unsolved'. The learn session can hand you back to it.[/dim]",
            )
            retire_state(state.slug)
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
                conn, console, backend, problem, state, warmup=warmup
            )
            if outcome == "solved":
                if warmup and card is not None:
                    grade = _ask_grade(console, len(state.hints))
                    summary = scheduler.record_grade(conn, card, grade)
                    _show_card_update(console, card, summary, lapse=(grade == 1))
                    retire_state(state.slug)
                    return "warmup_done"
                scheduler.ensure_card(
                    conn, user_id, problem["pattern"], reflection=reflection
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
