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
import tempfile
import time
from pathlib import Path

from dataclasses import asdict, dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dojo import complexity, scheduler, static
from dojo.config import VENV_PYTHON, WORKBENCH_DIR
from dojo.db import (
    dumps_json,
    get_or_create_user,
    insert_revision,
    iso_from_epoch,
    loads_json,
    now,
    update_revision,
)
from dojo.editor import ensure_ide_config, launch as launch_editor
from dojo.guard import guard
from dojo.judge import (
    JUDGE_CASES,
    ORACLES,
    PROFILER_INPUTS,
    reference_source,
    run_cases,
)
from dojo.judge.compare import check_equal
import dojo.profiler.probe as probe_mod

from dojo.profiler import growth
from dojo.render import render_ai, review_markdown
from dojo.session import workbench
from dojo.session.learn import resolve_pattern, run_learn
from dojo.session.state import (
    WorkbenchState,
    load_state,
    retire_state,
    save_state,
)
from dojo.terminal import confirm_typo, make_prompt, patch_console
from dojo.tutor import TIER_NAMES, ask_tutor, review
from dojo.tutor.backend import Role
from dojo.tutor.prompts import DISCUSSION_SYSTEM, build_discussion_prompt
from dojo.ui import table as ui_table

GENERATED_CASES = 30

#: The session's commands, per phase (v0.13). One table, so "add a command"
#: cannot forget a mode — which is exactly how `check` and `open` came to be
#: missing after a submit, and how the words `check`/`open` ended up being sent
#: to the AI as questions.
SOLVE_COMMANDS = ("open", "check", "learn", "report", "submit", "quit")
POST_COMMANDS = ("polish", "done")
COMMANDS_HINT = "Ask a question, or: open · check · learn · submit · quit"
POST_COMMANDS_HINT = "Ask a question, or: polish (back to solving, with the discussion tutor) · done"

TEMPLATE_STUB_COMMENT = (
    "# Solve it. Use `dojo check` / `dojo hint` from a second terminal."
)


def _render_template(problem: sqlite3.Row) -> str:
    """The blank workbench file — a thin alias for `session.workbench`, which
    owns the template, the fenced examples block, and the chrome-stripped view
    every AI reader gets (v0.13)."""
    return workbench.render_template(problem)


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
    expected: str | None, claimed: str | None, measured: str | None
) -> dict[str, str]:
    """The three pairwise comparisons of one axis.

    ``measured`` is the class the *differential* measurement concluded — the
    reference's class when the student's growth matches it, or the class the
    trend names when it does not. It is None whenever the probe could not
    resolve one, which reads as incomparable rather than as agreement."""
    return {
        "claim_vs_expected": complexity.compare(claimed, expected),
        "measured_vs_claimed": complexity.compare(measured, claimed),
        "measured_vs_expected": complexity.compare(measured, expected),
    }


def _show_complexity_table(
    console: Console,
    expected_time: str | None,
    expected_space: str | None,
    claimed_time: str | None,
    claimed_space: str | None,
    measurement: "Measurement",
) -> None:
    """The three-way table (v0.12).

    The measured column holds what the probe actually concluded, which is always
    a claim about the *comparison* with the reference, never a fitted class: it
    shows the derived class when the trend supports one and the verdict when it
    does not. Red still means disagreement; incomparable axes are named rather
    than left blank."""
    table = ui_table("Complexity: expected vs. claimed vs. measured")
    table.add_column("")
    table.add_column("Expected")
    table.add_column("You claimed")
    table.add_column("Measured")
    table.add_column("vs reference")
    notes: list[str] = []
    asides: list[str] = []

    def axis_cells(axis: str, expected, claimed, verdict) -> tuple:
        measured = verdict.student_class if verdict.resolved else None
        outcomes = _axis_outcomes(expected, claimed, measured)
        disagree = {k for k, v in outcomes.items() if v == complexity.DISAGREE}
        incomparable = {k for k, v in outcomes.items() if v == complexity.INCOMPARABLE}
        for key in ("claim_vs_expected", "measured_vs_claimed", "measured_vs_expected"):
            if key in disagree:
                notes.append(f"{axis}: {key.replace('_', ' ')}")
        if verdict.kind in (growth.UNRESOLVED, growth.UNREFERENCED, growth.FAILED):
            asides.append(f"{axis}: {verdict.note}")
        elif incomparable and expected and claimed and measured:
            asides.append(
                f"{axis}: the probe scales a single size parameter, so it does not "
                "speak to a claim in other variables"
            )
        elif verdict.steps:
            asides.append(f"{axis}: {verdict.note}")
        agree_all = (
            not disagree
            and not incomparable
            and all(v is not None for v in (expected, claimed, measured))
            and all(outcome == complexity.AGREE for outcome in outcomes.values())
        )

        def cell(value, red: bool):
            text = value or "—"
            if red:
                return Text(text, style="red")
            if agree_all:
                return Text(text, style="green")
            return text

        return (
            cell(expected, "claim_vs_expected" in disagree or "measured_vs_expected" in disagree),
            cell(claimed, "claim_vs_expected" in disagree or "measured_vs_claimed" in disagree),
            cell(measured or verdict.label, "measured_vs_claimed" in disagree or "measured_vs_expected" in disagree),
        )

    for axis, expected, claimed, verdict in (
        ("time", expected_time, claimed_time, measurement.time),
        ("space", expected_space, claimed_space, measurement.space),
    ):
        expected_cell, claimed_cell, measured_cell = axis_cells(axis, expected, claimed, verdict)
        table.add_row(
            axis.capitalize(), expected_cell, claimed_cell, measured_cell,
            verdict.trend_label,
        )
    console.print(table)
    if notes:
        console.print(
            "[yellow]Red cells disagree (evidence, not verdicts) — investigate "
            "whether it's the algorithm, the claim, or the reference.[/yellow]"
        )
    for line in dict.fromkeys(asides):
        console.print(f"[dim]{line}[/dim]")


def _show_measurement(console: Console, measurement: "Measurement") -> None:
    """Anything the probe found that the table cannot express: a crash at scale,
    or an output that disagrees with the reference."""
    if measurement.failure is not None:
        where = f" at n={measurement.failed_at:,}" if measurement.failed_at else ""
        console.print(
            f"[red]✗ Your code failed{where}: {measurement.failure}[/red]"
        )
        console.print(
            "[dim]That is a real finding, not a measurement artifact: the scale "
            "probe runs your code on large inputs, which the judge's cases "
            "(n ≤ 12) never do.[/dim]"
        )
    if measurement.mismatch_at is not None:
        console.print(
            f"[red]✗ Output differs from the reference at n={measurement.mismatch_at:,}"
            f"{' (confirmed against the oracle)' if measurement.mismatch_confirmed else ''}[/red]"
        )
        if not measurement.mismatch_confirmed:
            console.print(
                "[dim]The oracle could not run at that size, so this could be a "
                "curation problem rather than a bug in your code — `dojo report` "
                "audits the problem.[/dim]"
            )
    if not measurement.reference_used:
        console.print(
            "[dim]No reference solution is registered for this problem, so the "
            "growth check has nothing to compare against. `dojo reference "
            f"{measurement.slug}` adds one.[/dim]"
        )
    elif measurement.reference_failed_at is not None:
        console.print(
            f"[yellow]The reference itself failed at n={measurement.reference_failed_at:,}"
            f" ({measurement.reference_failure}) — the comparison stops there. "
            "That is a curation problem, not a fact about your code: "
            "`dojo report` audits it.[/yellow]"
        )


def _measurement_note(verdict: "growth.Verdict") -> str | None:
    """What the reviewer needs to know about a measurement — it used to be handed
    a bare class and left to guess whether a disagreement was evidence or an
    artifact."""
    if verdict is None:
        return None
    if verdict.resolved:
        return verdict.note
    return f"{verdict.note} — NOT evidence against the student's claim"


def _write_template(problem: sqlite3.Row, force: bool = False) -> None:
    """Write the blank template, refusing to write one that cannot compile."""
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKBENCH_DIR / f"{problem['slug']}.py"
    if path.exists() and not force:
        return
    source = workbench.template_for(problem)
    path.write_text(source)


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
    analysis = static.analyze(
        code_path, source=workbench.student_view(code_path.read_text(), problem)
    )
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)
    return report.all_passed


@dataclass
class Measurement:
    """What the scale probe concluded for one attempt (v0.12).

    Deliberately not a fitted complexity class: the probe measures the student's
    cost curve *against a reference implementation*, so every field here is
    either a paired comparison or a fact about running the code at scale."""

    slug: str
    time: "growth.Verdict"
    space: "growth.Verdict"
    reference_used: bool = False
    failure: str | None = None
    failed_at: int | None = None
    mismatch_at: int | None = None
    mismatch_confirmed: bool = False
    reference_failed_at: int | None = None
    reference_failure: str | None = None
    points: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "time": asdict(self.time),
            "space": asdict(self.space),
            "reference_used": self.reference_used,
            "failure": self.failure,
            "failed_at": self.failed_at,
            "mismatch_at": self.mismatch_at,
            "mismatch_confirmed": self.mismatch_confirmed,
            "reference_failed_at": self.reference_failed_at,
            "reference_failure": self.reference_failure,
            "points": self.points,
        }


def _skipped_measurement(slug: str, note: str) -> Measurement:
    verdict = growth.Verdict(
        kind=growth.UNREFERENCED,
        trend=None,
        student_class=None,
        reference_class=None,
        steps=None,
        note=note,
    )
    return Measurement(slug=slug, time=verdict, space=verdict)


def _reference_target(slug: str, directory: Path) -> "probe_mod.Target | None":
    """Write the registered reference somewhere the probe can import it."""
    source = reference_source(slug)
    if not source:
        return None
    path = directory / f"reference_{slug}.py"
    path.write_text(source)
    from dojo.judge import REFERENCES

    return probe_mod.Target("reference", path, REFERENCES[slug].__name__)


def _probe_settings(slug: str) -> tuple[int | None, str]:
    """Per-problem probe policy from the curation overrides: an optional size cap
    (when the algorithm's cost model only holds below some n) and the comparison
    mode for the output check."""
    from dojo.bank import load_overrides

    entry = load_overrides().get(slug)
    if entry is None:
        return None, "strict"
    return entry.probe_max_n, entry.scale_compare


def _oracle_confirms(slug: str, n: int) -> bool:
    """At the disputed size, does the brute-force oracle side with the reference?

    The mismatch we found is student != reference. If the oracle agrees with the
    reference there, the student's output is the wrong one and this is a real
    bug. If the oracle cannot run at that size — or the problem has no oracle —
    the finding stays *unconfirmed*, because it might equally be the reference
    that is wrong, and that is a curation problem rather than the student's."""
    oracle = ORACLES.get(slug)
    generator = PROFILER_INPUTS.get(slug)
    reference = _live_reference(slug)
    if oracle is None or generator is None or reference is None:
        return False
    _, compare = _probe_settings(slug)
    if compare == "none":
        return False
    args = generator(n, random.Random(f"confirm-{n}"))
    try:
        return check_equal(reference(*args), oracle(*args), compare)
    except Exception:  # noqa: BLE001 - the anchor could not run at this size
        return False


def _live_reference(slug: str):
    from dojo.judge import REFERENCES

    return REFERENCES.get(slug)


def _measure_complexity(
    console: Console, problem: sqlite3.Row, code_path: Path
) -> Measurement:
    """Run the scale probe: student against the canonical reference, at a ladder
    of sizes, reporting failures and the growth comparison (v0.12)."""
    slug = problem["slug"]
    generator = PROFILER_INPUTS.get(slug)
    if generator is None:
        console.print(
            "[dim]No profiler input registered for this problem — skipping the "
            "scale probe.[/dim]"
        )
        return _skipped_measurement(
            slug, "this problem has no registered probe input to measure with"
        )

    max_n, compare = _probe_settings(slug)
    sizes = probe_mod.ladder(max_n or probe_mod.DEFAULT_MAX_N)
    declared_time = complexity.parse(problem["expected_time"])
    declared_space = complexity.parse(problem["expected_space"])

    console.print(
        f"[bold]Scale probe[/bold] (n = {sizes[0]:,} … {sizes[-1]:,}, "
        "student paired with the reference)..."
    )
    with tempfile.TemporaryDirectory(prefix="dojo_probe_") as tmp:
        reference = _reference_target(slug, Path(tmp))
        if reference is None:
            console.print(
                "[dim]No canonical reference registered — measuring your code "
                "alone (duration only).[/dim]"
            )
        with guard(
            console, "the scale probe", "grading continues without a measurement"
        ) as g:
            g.value = probe_mod.run_probe(
                probe_mod.Target("yours", code_path, problem["function_name"]),
                generator,
                reference,
                sizes=sizes,
                compare=compare if compare != "none" else "strict",
            )
        if not g.ok:
            return _skipped_measurement(
                slug, f"the probe could not run: {g.error}"
            )
        result = g.value

    failure_point = result.first_failure()
    failure = failure_point.student.error if failure_point else None
    failed_at = failure_point.n if failure_point else None
    reference_failure_point = result.reference_failure()

    mismatch_point = result.first_mismatch() if compare != "none" else None
    mismatch_at = mismatch_point.n if mismatch_point else None
    if mismatch_at is not None and mismatch_at > sizes[0]:
        mismatch_at = probe_mod.locate_mismatch(
            probe_mod.Target("yours", code_path, problem["function_name"]),
            reference,
            generator,
            mismatch_at,
            compare=compare,
        )
    confirmed = mismatch_at is not None and _oracle_confirms(slug, mismatch_at)

    time_verdict = growth.verdict(
        result.time_ratios,
        declared_class=declared_time,
        has_reference=result.has_reference,
        failure=failure,
        failed_at=failed_at,
    )
    space_verdict = growth.verdict(
        result.space_ratios,
        declared_class=declared_space,
        has_reference=result.has_reference,
    )
    return Measurement(
        slug=slug,
        time=time_verdict,
        space=space_verdict,
        reference_used=result.has_reference,
        failure=failure,
        failed_at=failed_at,
        mismatch_at=mismatch_at,
        mismatch_confirmed=confirmed,
        reference_failed_at=(
            reference_failure_point.n if reference_failure_point else None
        ),
        reference_failure=(
            reference_failure_point.reference.error if reference_failure_point else None
        ),
        points=[
            {
                "n": p.n,
                "student_ms": p.student.ms,
                "reference_ms": p.reference.ms if p.reference else None,
                "ratio": p.time_ratio,
                "space_ratio": p.space_ratio,
                "error": p.student.error,
                "spread": round(p.spread, 4),
            }
            for p in result.points
        ],
    )


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
        # Any "I'm done" answer proceeds. "quit"/"done" used to fall through to
        # the guidance line and ask again — an inescapable prompt loop for anyone
        # who typed the command they use everywhere else in dojo (found while
        # writing a test that ran out of canned answers).
        if edit in ("", "ok", "y", "yes", "quit", "q", "done"):
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
    """Write the attempt head **and append its revision**, in one transaction.

    The head row is created by this session's first submit and updated by every
    later one (v0.11: an attempt exists iff the student submitted). The revision
    is the immutable record of the version that was just judged — which is what
    makes polish non-destructive (v0.13): only the head moves forward.
    """
    code = state.code_path.read_text()
    submitted_at = now()
    hints_json = dumps_json(state.hints)
    duration = round(time.time() - state.started_epoch, 1)
    if state.attempt_id is None:
        cur = conn.execute(
            """
            INSERT INTO attempts
                (user_id, problem_id, kind, status, code, started_at, submitted_at,
                 duration_seconds, hint_count, hints)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                problem["id"],
                state.kind,
                report.status,
                code,
                iso_from_epoch(state.started_epoch),
                submitted_at,
                duration,
                len(state.hints),
                hints_json,
            ),
        )
        state.attempt_id = cur.lastrowid
    else:
        conn.execute(
            "UPDATE attempts SET status = ?, code = ?, submitted_at = ?, "
            "duration_seconds = ?, hint_count = ?, hints = ? WHERE id = ?",
            (
                report.status,
                code,
                submitted_at,
                duration,
                len(state.hints),
                hints_json,
                state.attempt_id,
            ),
        )
    state.revision = insert_revision(
        conn,
        state.attempt_id,
        kind="polish" if state.phase == "polish" else "submit",
        code=code,
        status=report.status,
        hints=hints_json,
    )
    update_revision(
        conn,
        state.attempt_id,
        state.revision,
        judge=dumps_json(
            {
                "status": report.status,
                "passed": report.passed,
                "total": report.total,
                "failures": [
                    {
                        "label": r.label,
                        "expected": str(r.expected)[:200],
                        "got": str(r.got)[:200],
                        "error": r.error,
                    }
                    for r in report.results
                    if not r.passed
                ][:10],
            }
        ),
    )
    conn.commit()
    save_state(state)
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

    analysis = static.analyze(
        code_path, source=workbench.student_view(code_path.read_text(), problem)
    )
    if analysis.flags or analysis.notes:
        _show_static(console, analysis)

    claimed_time_raw, claimed_space_raw = _ask_complexity_claims(console)
    claimed_time = complexity.parse(claimed_time_raw)
    claimed_space = complexity.parse(claimed_space_raw)

    measurement = _measure_complexity(console, problem, code_path)
    _show_measurement(console, measurement)
    _show_complexity_table(
        console,
        problem["expected_time"],
        problem["expected_space"],
        claimed_time,
        claimed_space,
        measurement,
    )

    # Reflect first, so the reviewer can comment on the reflection. A polished
    # re-submit does not re-ask: the reflection belongs to the first solve (the
    # old `polish` never asked for one either), and the student is mid-edit.
    reflection = None
    if not warmup and state.phase != "polish":
        reflection = _ask_question(
            console,
            "Reflection — what was the key insight, and when would you reach "
            "for this again?",
        )

    # A polished re-submit asks before paying for a second review (the old
    # `polish` did): re-grading without re-reviewing is a normal thing to want,
    # and re-reviewing is the expensive half.
    review_json: dict = {}
    if state.phase == "polish" and state.attempt_id is not None:
        previous = conn.execute(
            "SELECT review FROM attempts WHERE id = ?", (state.attempt_id,)
        ).fetchone()
        review_json = loads_json(previous["review"], {}) if previous else {}
        if make_prompt(console)("Review again? [y/N]: ").strip().lower() not in ("y", "yes"):
            console.print("[dim]Review kept as-is.[/dim]")
    if review_json:
        _show_review(console, review_json)

    if not review_json:
        console.print(
            "[bold]AI review[/bold] (post-submission; the reviewer critiques, "
            "it never repairs)..."
        )
    code = workbench.student_view(code_path.read_text(), problem)
    with guard(console, "the reviewer", "the attempt is still recorded") as g:
        g.value = review(
            backend,
            problem["statement"],
            code,
            claimed_time_raw,
            claimed_space_raw,
            measurement.time.label,
            measurement.space.label,
            problem["expected_time"],
            problem["expected_space"],
            static_analysis=analysis,
            reflection=reflection,
            measured_time_note=_measurement_note(measurement.time),
            measured_space_note=_measurement_note(measurement.space),
        )
    if not review_json:
        review_json = g.value if g.ok else {}
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
            measured_time_class = ?, measured_time_r2 = NULL,
            measured_space_class = ?, measured_space_r2 = NULL,
            measurement = ?, review = ?, reflection = ?, static_analysis = ?,
            polished = polished + ?, ai_provenance = COALESCE(?, ai_provenance)
        WHERE id = ?
        """,
        (
            # The head keeps the *raw* artifact (what actually ran, chrome and
            # all) — the stripped view goes to the AI, never to storage.
            code_path.read_text(),
            now(),
            round(time.time() - state.started_epoch, 1),
            len(state.hints),
            dumps_json(state.hints),
            claimed_time_raw,
            claimed_space_raw,
            measurement.time.student_class,
            measurement.space.student_class,
            dumps_json(measurement.to_json()),
            dumps_json(review_json) if review_json else None,
            reflection,
            dumps_json(analysis.to_dict()),
            1 if state.phase == "polish" else 0,
            dumps_json(backend.identity()) if review_json else None,
            state.attempt_id,
        ),
    )
    # The artifacts belong to the revision whose code produced them (v0.13):
    # the claims, the measurement, the review and the static analysis all attach
    # to *that* version, so a later polish cannot rewrite their history.
    if state.revision is not None:
        update_revision(
            conn,
            state.attempt_id,
            state.revision,
            status="correct",
            self_reported_time=claimed_time_raw,
            self_reported_space=claimed_space_raw,
            measurement=dumps_json(measurement.to_json()),
            static_analysis=dumps_json(analysis.to_dict()),
            review=dumps_json(review_json) if review_json else None,
            reflection=reflection,
            hints=dumps_json(state.hints),
        )
    conn.commit()
    console.print(
        Panel(
            f"[bold green]Solved:[/bold green] {problem['title']} — attempt recorded.\n"
            f"Claimed: {claimed_time or '?'} / {claimed_space or '?'}  ·  "
            f"Measured: {measurement.time.label} / {measurement.space.label}  ·  "
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


def _discuss(conn: sqlite3.Connection, console: Console, backend, problem: sqlite3.Row, state: WorkbenchState, question: str) -> None:
    """Post-solve chat: the never-solve boundary lifts, the transcript
    persists on the attempt row. The prompt carries the submitted code so
    the model grounds on what actually ran (v0.8.1)."""
    row = conn.execute(
        "SELECT discussion FROM attempts WHERE id = ?", (state.attempt_id,)
    ).fetchone()
    if row is None:
        # A stale state file can outlive its attempt row; a subscript on None
        # used to crash the post-solve loop (v0.13 audit, S2.9).
        console.print(
            "[yellow]This attempt is no longer in the database — the "
            "conversation can't be saved. `done` to close the session.[/yellow]"
        )
        return
    history = loads_json(row["discussion"], [])
    prompt = build_discussion_prompt(
        problem["statement"],
        workbench.student_view(state.code_path.read_text(), problem),
        history,
        question,
    )
    with guard(console, "the discussion tutor", "ask again in a moment") as g:
        g.value = backend.chat(
            Role.DISCUSSION, DISCUSSION_SYSTEM, prompt
        )  # raw markdown (v0.10.3)
    if not g.ok:
        return
    answer = g.value
    render_ai(console, "tutor — post-solve discussion", answer, border_style="green")
    conn.execute(
        "UPDATE attempts SET discussion = ? WHERE id = ?",
        (dumps_json(history + [{"user": question, "tutor": answer}]), state.attempt_id),
    )
    conn.commit()


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
            f"problem: [bold]{card['slug']}[/bold] [dim]({card['pattern']})[/dim]\n"
            f"stability: {card['stability']:.2f} → {summary['stability']:.2f} days\n"
            f"difficulty: {card['difficulty']:.1f} → {summary['difficulty']:.1f}\n"
            f"next warm-up: [bold]{scheduler.due_phrase(summary['due_at'])}[/bold]",
            title="Card updated — lapse" if lapse else "Card updated",
            border_style="red" if lapse else "green",
        )
    )
    if not lapse and card["last_reflection"]:
        console.print(
            Panel(
                card["last_reflection"],
                title="Your last reflection on this problem",
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
    # Curated means "has a function name and at least one *parsed* visible test":
    # the old guard tested the truthiness of the JSON string, so a stored "[]"
    # passed it and the judge graded zero cases as a pass (v0.13 audit, S1.3).
    if not problem["function_name"] or not (
        loads_json(problem["visible_tests"], []) or []
    ):
        console.print(
            f"[red]'{slug}' is not curated yet (needs a function name and at "
            "least one visible test in data/problem_overrides.json).[/red]"
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
    try:
        _write_template(problem, force=is_new_session)
    except workbench.TemplateError as exc:
        console.print(f"[red]{exc}[/red]")
        return "error"
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
        with guard(console, "the tutor", "ask again in a moment") as g:
            g.value = ask_tutor(
                backend,
                problem["statement"],
                workbench.student_view(state.code_path.read_text(), problem),
                state.tier,
                question,
                state.hints,
            )
        if not g.ok:
            # An API/transport failure is not a leak and not a session-ender:
            # the tier does not advance, nothing is recorded, and the prompt
            # comes back.
            return
        result = g.value
        if not result.delivered:
            if result.audit_failed:
                # Distinct from a leak: the answer may be fine, but nothing
                # verified it, and never-solve is not delivered on trust (v0.13).
                console.print(
                    "[yellow]The leak check couldn't be read, so that answer was "
                    "discarded rather than shown. Ask again.[/yellow]"
                )
            else:
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
    # One loop, two phases (v0.13). `state.phase` decides which commands exist
    # and which agent answers a question; `polish` moves back to solving with the
    # discussion agent, so the phase is data rather than which `while` you are in.
    while True:
        # `phase == "post_solve"`, not "!= solving": the polish phase *is* a
        # solving phase (open/check/submit), with the discussion agent answering.
        post_solve = state.phase == "post_solve"
        hint = POST_COMMANDS_HINT if post_solve else COMMANDS_HINT
        commands = POST_COMMANDS if post_solve else SOLVE_COMMANDS
        raw = prompt(
            "[bold cyan]dojo ›[/bold cyan] ",
            hint=f"[dim]{hint}[/dim]",
        ).strip()
        if not raw:
            continue
        cmd, _, rest = raw.partition(" ")
        fixed = confirm_typo(console, cmd, list(commands) + ["q", "p", "c", "o", "s"])
        if fixed is not None:
            raw = fixed
            cmd, _, rest = fixed.partition(" ")

        if post_solve:
            if cmd in ("done", "quit", "q") and not rest:
                retire_state(state.slug)
                return "solved"
            if cmd in ("polish", "p") and not rest:
                # Back to solving, with the discussion agent still answering:
                # `open`, `check`, `submit` are available again, and questions
                # may show code because the boundary lifted at the first grade.
                state.phase = "polish"
                state.agent = "discussion"
                save_state(state)
                console.print(
                    "[dim]Back to solving — `open` · `check` · `submit` are "
                    "yours again, and questions go to the post-solve tutor "
                    "(solutions allowed).[/dim]"
                )
                continue
            if cmd in ("open", "check", "o", "c", "submit", "s", "learn", "l") and not rest:
                # Solving-mode commands: say where they went instead of quietly
                # sending the word to the model as a question (the exact failure
                # the v0.13 audit reproduced by typing `check` after a submit).
                console.print(
                    f"[dim]`{cmd}` is a solving-mode command — `polish` takes you "
                    "back there (with the post-solve tutor answering).[/dim]"
                )
                continue
            _discuss(conn, console, backend, problem, state, raw)
            continue

        if cmd in ("polish", "p", "done") and not rest:
            # Post-solve commands, before there is a solve: say where they live
            # rather than sending the word to the tutor as a question.
            console.print(
                "[dim]`polish` and `done` come after a submit — `submit` when "
                "your code passes, or `quit` to leave.[/dim]"
            )
            continue
        if cmd in ("q", "quit") and not rest:
            if state.attempt_id is not None:
                # Polishing: the attempt already exists, so there is nothing to
                # abandon — the session simply ends and the record (with every
                # version of it) stays. The outcome stays "quit": the vocabulary
                # callers switch on does not change just because a row exists.
                console.print(
                    "[dim]Session ended. Your attempt and its versions are "
                    "saved.[/dim]"
                )
                retire_state(state.slug)
                return "quit"
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
            if state.attempt_id is not None:
                console.print(
                    "[dim]You've already submitted — the post-solve tutor can "
                    "show you a different approach directly. Ask away.[/dim]"
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
                    # ... one transaction, and only if this attempt has not
                    # graded the card already (v0.13: a crash between the two
                    # writes used to apply the grade twice).
                    claimed = conn.execute(
                        "UPDATE attempts SET recall_grade = ? "
                        "WHERE id = ? AND recall_grade IS NULL",
                        (grade, state.attempt_id),
                    ).rowcount
                    if not claimed:
                        console.print(
                            "[dim]This attempt already updated the card — not "
                            "grading it twice.[/dim]"
                        )
                        retire_state(state.slug)
                        return "warmup_done"
                    summary = scheduler.record_grade(conn, card, grade, commit=False)
                    conn.commit()
                    _show_card_update(console, card, summary, lapse=(grade == 1))
                    retire_state(state.slug)
                    return "warmup_done"
                # A first solve carries evidence about the pattern in its own
                # hint count — seed the card with it rather than a flat default.
                scheduler.ensure_item_card(
                    conn,
                    user_id,
                    problem["slug"],
                    problem["pattern"],
                    reflection=reflection,
                    grade=suggested_grade(state.hints),
                )
                state.phase = "post_solve"
                state.agent = "discussion"
                save_state(state)
        else:
            # Bare questions — and command words with extra text ("check my
            # solution...") — are questions, never "Unknown command" (v0.10.1).
            if state.agent == "discussion":
                # Polishing (v0.13): the boundary lifted when the solve was
                # graded, so questions go to the post-solve agent — which may
                # show code and grounds on the file as it stands right now.
                _discuss(conn, console, backend, problem, state, raw)
                continue
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
        console.print(
            "[green]No warm-ups due[/green] — "
            f"[dim]next warm-up {scheduler.due_hint(conn, user_id)}.[/dim]"
        )
        return []
    console.print(f"[bold]Warm-up: {len(cards)} card(s) due.[/bold]")
    outcomes = []
    for card in cards:
        problem = scheduler.item_problem(conn, card)
        if problem is None:
            # The card names its own problem now, so this means the problem is
            # gone or no longer curated — say which and where to look, instead of
            # deferring quietly for days (v0.13 audit, S2.11).
            console.print(
                f"[yellow]'{card['slug']}' can no longer be re-solved (it is not "
                f"curated in the bank) — deferring this card a day. "
                f"`dojo report {card['slug']}` audits its curation.[/yellow]"
            )
            scheduler.defer(conn, card, days=1.0)
            continue
        try:
            _write_template(problem, force=True)
        except workbench.TemplateError as exc:
            console.print(f"[yellow]{exc} — skipping this warm-up.[/yellow]")
            scheduler.defer(conn, card, days=1.0)
            continue
        outcome = run_day(
            conn, console, backend, problem["slug"], user_name,
            open_editor=False, warmup=True, card=card,
        )
        outcomes.append(outcome)
        if outcome in ("quit", "practice"):
            break
    remaining = scheduler.due_now_count(conn, user_id)
    if remaining:
        # Never let the pile grow invisibly: per-problem cards mean several can
        # be due at once, and `--limit` is the knob.
        console.print(
            f"[dim]{remaining} more card(s) still due — `dojo warmup --limit "
            f"{remaining}` drains them.[/dim]"
        )
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
