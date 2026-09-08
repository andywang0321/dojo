"""The daily flow: one problem, end to end.

  solve in $EDITOR (via `open`, non-blocking) → check (visible tests)
  → hint ladder → submit → judge (visible + generated + oracle)
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

from dojo import complexity, scheduler
from dojo.config import WORKBENCH_DIR
from dojo.db import dumps_json, get_or_create_user, loads_json, now
from dojo.editor import launch as launch_editor
from dojo.judge import JUDGE_CASES, PROFILER_INPUTS, run_cases
from dojo.profiler import classify, measure
from dojo.session.state import (
    WorkbenchState,
    load_state,
    retire_state,
    save_state,
)
from dojo.tutor import TIER_NAMES, ask_tutor, de_markdown, review

GENERATED_CASES = 30

COMMANDS_HINT = (
    "[dim]Commands: [b]check[/b] · [b]hint <text>[/b] · "
    "[b]open[/b] · [b]submit[/b] · [b]quit[/b][/dim]"
)

TEMPLATE_HEADER = '''"""
{statement}
"""


def {function_name}{signature}:
    # Solve it. Use `dojo check` / `dojo hint` from a second terminal.
    raise NotImplementedError
'''

# v0: signatures for curated problems live here; move into
# data/problem_overrides.json when the bank grows.
SIGNATURES = {
    "array_intersection": "(A: list[int], B: list[int]) -> list[int]",
    "binary_tree_diameter": "(root: list | None) -> int",
    "car_fleet": "(target: int, position: list[int], speed: list[int]) -> int",
    "container_with_most_water": "(height: list[int]) -> int",
    "contains_duplicate": "(nums: list[int]) -> bool",
    "correlation": "(X: list, Y: list) -> float",
    "daily_temperatures": "(temperatures: list[int]) -> list[int]",
    "evaluate_reverse_polish_notation": "(tokens: list[str]) -> int",
    "generate_parentheses": "(n: int) -> list[str]",
    "group_anagrams": "(strs: list[str]) -> list[list[str]]",
    "k_closest_points": "(k: int, points: list[list[int]]) -> list[list[int]]",
    "k_smallest_elem_matrix": "(k: int, matrix: list[list[int]]) -> int",
    "largest_rectangle_in_histogram": "(heights: list[int]) -> int",
    "longest_consecutive_sequence": "(nums: list[int]) -> int",
    "max_prod_3_nums": "(A: list[int]) -> int",
    "mirror_image_binary_tree": "(root: list | None) -> bool",
    "peak_elements": "(nums: list[int]) -> int",
    "products_of_array_except_self": "(nums: list[int]) -> list[int]",
    "sum_largest_contiguous_subarray": "(A: list[int]) -> int",
    "three_sum": "(nums: list[int]) -> list[list[int]]",
    "top_k_frequent_elements": "(nums: list[int], k: int) -> list[int]",
    "trapping_rain_water": "(height: list[int]) -> int",
    "two_sum": "(nums: list[int], target: int) -> list[int]",
    "two_sum_2": "(numbers: list[int], target: int) -> list[int]",
    "valid_anagram": "(s: str, t: str) -> bool",
    "valid_palindrome": "(s: str) -> bool",
    "valid_parentheses": "(s: str) -> bool",
    "valid_sudoku": "(board: list[list[str]]) -> bool",
}


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
            args, expected = generator(n, rng)
            cases.append({"args": args, "expected": expected, "label": f"generated {i + 1}"})
    return cases


def _show_case_failures(console: Console, report) -> None:
    table = Table(title="Failed cases")
    table.add_column("Case")
    table.add_column("Expected")
    table.add_column("Got")
    table.add_column("Error")
    for r in report.results:
        if r.passed:
            continue
        table.add_row(
            r.label,
            str(r.expected)[:60],
            str(r.got)[:60],
            (r.error or "")[:60],
        )
    console.print(table)


def _show_complexity_table(
    console: Console,
    expected_time: str | None,
    expected_space: str | None,
    claimed_time: str | None,
    claimed_space: str | None,
    measured_time: str | None,
    measured_space: str | None,
) -> None:
    table = Table(title="Complexity: expected vs. claimed vs. measured")
    table.add_column("")
    table.add_column("Expected")
    table.add_column("You claimed")
    table.add_column("Measured")
    table.add_column("Flag")
    time_flag = "ok"
    space_flag = "ok"
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
    time_flag = "⚠ " + ", ".join(n for n in notes if n.startswith("time")) if any(
        n.startswith("time") for n in notes
    ) else "ok"
    space_flag = "⚠ " + ", ".join(n for n in notes if n.startswith("space")) if any(
        n.startswith("space") for n in notes
    ) else "ok"
    table.add_row("Time", expected_time or "-", claimed_time or "-", measured_time or "-", time_flag)
    table.add_row("Space", expected_space or "-", claimed_space or "-", measured_space or "-", space_flag)
    console.print(table)
    if notes:
        console.print(
            "[yellow]Mismatches are evidence, not verdicts — investigate whether "
            "it's the algorithm, the claim, or measurement noise.[/yellow]"
        )


def _write_template(problem: sqlite3.Row, force: bool = False) -> None:
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKBENCH_DIR / f"{problem['slug']}.py"
    if path.exists() and not force:
        return
    path.write_text(
        TEMPLATE_HEADER.format(
            statement=problem["statement"],
            function_name=problem["function_name"],
            signature=SIGNATURES.get(problem["slug"], ""),
        )
    )


def _check(console: Console, problem: sqlite3.Row, code_path: Path) -> bool:
    cases = [
        {**c, "label": f"visible {i + 1}"}
        for i, c in enumerate(loads_json(problem["visible_tests"], []) or [])
    ]
    report = run_cases(code_path, problem["function_name"], cases)
    if report.all_passed:
        console.print(f"[green]✓ {report.passed}/{report.total} visible cases passed[/green]")
        return True
    _show_case_failures(console, report)
    return False


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

    claimed_time_raw = console.input("State your time complexity and why (e.g. 'O(n) because one pass'): ")
    claimed_space_raw = console.input("State your space complexity and why: ")
    claimed_time = complexity.parse(claimed_time_raw)
    claimed_space = complexity.parse(claimed_space_raw)

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
            sfit = classify([n for n, _ in m.space_points], [s for _, s in m.space_points])
            measured_space, space_r2 = sfit.best_class, round(sfit.r2, 3)
        if m.dropped:
            console.print(f"[dim](dropped sizes: {', '.join(m.dropped)})[/dim]")
    else:
        console.print("[dim]No profiler input generator registered for this problem — skipping measurement.[/dim]")

    _show_complexity_table(
        console,
        problem["expected_time"],
        problem["expected_space"],
        claimed_time,
        claimed_space,
        measured_time,
        measured_space,
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
    )
    if "error" in review_json:
        console.print("[yellow]Reviewer unavailable (non-JSON response) — review skipped.[/yellow]")
        review_json = {}
    else:
        _show_review(console, review_json)

    reflection = None
    if not warmup:
        reflection = console.input(
            "Reflection — what was the key insight, and when would you reach for this again? "
        )

    conn.execute(
        """
        UPDATE attempts SET
            code = ?, status = 'correct', submitted_at = ?,
            duration_seconds = ?,
            hint_count = ?, hints = ?,
            self_reported_time = ?, self_reported_space = ?,
            measured_time_class = ?, measured_time_r2 = ?,
            measured_space_class = ?, measured_space_r2 = ?,
            review = ?, reflection = ?
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


def _show_review(console: Console, review_json: dict) -> None:
    table = Table(title="AI review")
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
    ]
    for dim in dims:
        entry = review_json.get(dim, {})
        if isinstance(entry, dict):
            table.add_row(
                dim.replace("_", " "),
                str(entry.get("score", "?")),
                de_markdown(str(entry.get("comment", ""))),
            )
    console.print(table)
    if review_json.get("broader_picture"):
        console.print(Panel(de_markdown(str(review_json["broader_picture"])), title="Broader picture"))
    if review_json.get("overall_comment"):
        console.print(f"[italic]{de_markdown(str(review_json['overall_comment']))}[/italic]")


def _ask_grade(console: Console, hints: int) -> int:
    suggested = 4 if hints == 0 else 3 if hints == 1 else 2
    raw = console.input(
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

    while True:
        console.print(COMMANDS_HINT)
        raw = console.input("[bold cyan]dojo ›[/bold cyan] ").strip()
        if not raw:
            continue
        cmd, _, rest = raw.partition(" ")
        if cmd in ("q", "quit"):
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
            console.print(
                "[dim]Progress saved; attempt stays 'unsolved'. Next session "
                "starts fresh.[/dim]"
            )
            if warmup and card is not None:
                summary = scheduler.record_grade(conn, card, 1)
                _show_card_update(console, card, summary, lapse=True)
            retire_state(state.slug)
            return "quit"
        if cmd in ("c", "check"):
            _check(console, problem, state.code_path)
        elif cmd in ("o", "open"):
            console.print(launch_editor(state.code_path))
        elif cmd in ("h", "hint"):
            result = ask_tutor(
                backend,
                problem["statement"],
                state.code_path.read_text(),
                state.tier,
                rest or "I'm stuck",
                state.hints,
            )
            cleaned = de_markdown(result.text)
            state.hints.append(
                {"tier": result.tier, "user": rest or "I'm stuck", "hint": cleaned}
            )
            state.tier = min(result.tier + 1, 5)
            save_state(state)
            console.print(
                Panel(
                    cleaned,
                    title=f"hint · tier {result.tier} ({TIER_NAMES[result.tier]})"
                    + (f" · leak rating {result.leak_rating}" if result.leak_rating >= 3 else ""),
                    border_style="blue",
                )
            )
            console.print(f"[dim]Next hint will be tier {state.tier} ({TIER_NAMES[state.tier]}).[/dim]")
        elif cmd in ("s", "submit"):
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
                retire_state(state.slug)
                return "solved"
        else:
            console.print("[dim]Unknown command.[/dim]")


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
        if outcome == "quit":
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
