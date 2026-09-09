"""The dojo CLI.

  dojo                        the daily routine (warm-ups + a picked problem)
  dojo <slug>                 the daily routine on a specific problem
  dojo day [SLUG]             the same, explicitly (alias)
  dojo warmup                 run due warm-up retrievals only
  dojo learn [TOPIC]          learning mode (planned — see roadmap/next.md)
  dojo list [--pattern P]     the problem bank, with your solved status
  dojo check [SLUG]           visible tests on the current workbench
  dojo profile                your attempt history
  dojo history                attempts, newest first (see `show <id>`)
  dojo show ATTEMPT_ID        full detail of one attempt
  dojo progress               per-pattern proficiency, cards, score trends
  dojo user [NAME]            switch the active user (numbered picker without NAME)
  dojo curate [--text S|--file] AI-curate a new problem from a statement
  dojo fetch TITLE_SLUG       fetch a LeetCode problem and auto-curate it
  dojo setup                  re-run the setup wizard (key, user, PATH)
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dojo import scheduler
from dojo.bank import ensure_seeded
from dojo.config import DB_PATH, PROBLEMS_DIR, REPO_ROOT, load_conf, save_conf
from dojo.db import (
    connect,
    get_attempt,
    get_or_create_user,
    list_attempts,
    loads_json,
    now,
    review_trends,
)


class NeedsSetup(RuntimeError):
    """No user exists yet — the caller should run the setup wizard."""


def _active_user(conn, conf_user: str | None) -> str:
    """The active user: the conf file wins (validated), else the DB's sole
    user. Zero users means first run (NeedsSetup → wizard); a conf user
    missing from the DB is an error, never a silent typo'd account."""
    if conf_user:
        if not conn.execute(
            "SELECT 1 FROM users WHERE name = ?", (conf_user,)
        ).fetchone():
            raise RuntimeError(
                f"configured user '{conf_user}' is not in the database — "
                "run `dojo user` to list, or `dojo setup`."
            )
        return conf_user
    rows = conn.execute("SELECT name FROM users ORDER BY name").fetchall()
    if len(rows) == 1:
        return rows[0]["name"]
    if not rows:
        raise NeedsSetup("no users yet")
    raise RuntimeError(
        "multiple users — run `dojo user` to pick the active one."
    )


def _choose_user(console: Console, names: list[str]) -> str | None:
    """The `dojo user` numbered picker: returns the chosen name, or None on
    'q'."""
    while True:
        console.print("Users:")
        for i, name in enumerate(names, start=1):
            console.print(f"  {i}. {name}")
        raw = console.input("Pick a number (q to cancel): ").strip()
        if raw.lower() == "q":
            return None
        try:
            index = int(raw)
            if 1 <= index <= len(names):
                return names[index - 1]
        except ValueError:
            pass
        console.print("[red]Not a valid choice — try again.[/red]")


def _normalize_argv(argv: list[str], commands: set[str] | None = None) -> list[str]:
    """Bare `dojo` runs the daily routine; `dojo <slug>` targets a specific
    problem; anything else passes through untouched."""
    commands = COMMANDS if commands is None else commands
    if not argv:
        return ["day"]
    if argv[0] in commands or argv[0].startswith("-"):
        return argv
    return ["day"] + argv


def _cmd_user(args) -> int:
    console = Console()
    with connect(DB_PATH) as conn:
        names = [r["name"] for r in conn.execute("SELECT name FROM users ORDER BY name")]
    if args.name:
        target = args.name
        if target not in names:
            console.print(
                f"[red]Unknown user '{target}' — `dojo user` to list, "
                "`dojo setup` to add one.[/red]"
            )
            return 1
    elif not names:
        console.print("[red]No users yet — run `dojo setup`.[/red]")
        return 1
    elif len(names) == 1:
        target = names[0]
    else:
        target = _choose_user(console, names)
        if target is None:
            return 0
    current = load_conf().get("user")
    if target == current:
        console.print(f"[dim]'{target}' is already the active user.[/dim]")
        return 0
    save_conf({**load_conf(), "user": target})
    console.print(f"[green]Active user: {target}[/green]")
    return 0


def _make_path_installer(console: Console):
    """The interactive PATH step, shared by `dojo setup` and the first-run
    auto-trigger. Returns True when the wrapper was installed."""
    from dojo.setup import append_rc, install_wrapper, rc_line

    def path_install() -> bool:
        bin_dir = Path(os.path.expanduser("~")) / ".local" / "bin"
        console.print(
            f"[bold]Put `dojo` on your PATH?[/bold] I'll install a tiny wrapper "
            f"at {bin_dir / 'dojo'} that runs the live repo via `uv run`."
        )
        answer = console.input("Install? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            return False
        install_wrapper(bin_dir, str(REPO_ROOT))
        if str(bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
            shell = os.path.basename(os.environ.get("SHELL", ""))
            rc_name = ".zshrc" if "zsh" in shell else ".bashrc"
            rc_path = Path(os.path.expanduser("~")) / rc_name
            line = rc_line(str(bin_dir))
            if (
                console.input(
                    f"Append this line to {rc_path}? [y/N]\n  {line}\n"
                ).strip().lower()
                in ("y", "yes")
            ):
                append_rc(rc_path, line)
                console.print(
                    f"[dim]Appended to {rc_path} — restart your shell.[/dim]"
                )
            else:
                console.print(
                    f"[dim]Skipped. Add it yourself when ready: {line}[/dim]"
                )
        return True

    return path_install


def _cmd_setup(args) -> int:
    from dojo.setup import default_user_name, run_wizard

    console = Console()
    console.print("[dim]Checks: python ✓ · uv ✓ (wrapper uses `uv run`)[/dim]")
    run_wizard(
        console,
        dotenv_path=REPO_ROOT / ".env",
        conf_path=REPO_ROOT / "data" / "dojo.conf",
        db_path=DB_PATH,
        problems_dir=PROBLEMS_DIR,
        default_name=default_user_name(os.environ.get("USER"), _git_user_name()),
        user_override=args.user,
        key_getter=(lambda: "")
        if args.skip_key
        else (lambda: getpass.getpass("DeepSeek API key (Enter to skip): ")),
        path_install=None if args.no_path else _make_path_installer(console),
    )
    return 0


def _cmd_list(args) -> int:
    console = Console()
    with connect(DB_PATH) as conn:
        query = "SELECT * FROM problems"
        params: list = []
        if args.pattern:
            query += " WHERE pattern = ?"
            params.append(args.pattern)
        query += " ORDER BY pattern, difficulty, title"
        rows = conn.execute(query, params).fetchall()
        solved: dict[int, str] = {}
        user = getattr(args, "_user", None)
        if user:
            for r in conn.execute(
                """
                SELECT problem_id, status FROM attempts
                WHERE user_id = (SELECT id FROM users WHERE name = ?)
                """,
                (user,),
            ):
                solved[r["problem_id"]] = r["status"]
    table = Table(title="Problem bank")
    table.add_column("Problem")
    table.add_column("Difficulty")
    table.add_column("Pattern")
    table.add_column("Curated")
    table.add_column("Status")
    for r in rows:
        table.add_row(
            f"{r['title']} [dim]({r['slug']})[/dim]",
            r["difficulty"],
            r["pattern"],
            "✓" if r["function_name"] and r["visible_tests"] else "—",
            solved.get(r["id"], "—"),
        )
    console.print(table)
    console.print(
        f"{len(rows)} problems. Curated = has function name + visible tests "
        "(see data/problem_overrides.json), ready for `dojo day`."
    )
    return 0


def _print_footer(console: Console, conn, user_id: int) -> None:
    parts = [f"tomorrow: {scheduler.due_next_day_count(conn, user_id)} card(s) due"]
    trends = review_trends(conn, user_id)
    if trends:
        best = max(trends, key=lambda t: t["overall"])
        parts.append(f"best pattern: {best['pattern']} ({best['overall']})")
    console.print("[dim]" + " · ".join(parts) + "[/dim]")


def _cmd_day(args) -> int:
    from dojo.session import run_day, run_warmups
    from dojo.tutor import get_backend

    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        try:
            backend = get_backend()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        user_id = get_or_create_user(conn, user)
        due = scheduler.due_now_count(conn, user_id)
        console.print(f"[dim]Status: {due} warm-up card(s) due.[/dim]")
        if not args.skip_warmup:
            run_warmups(conn, console, backend, user, limit=2)
        slug = args.slug
        if slug is None:
            problem = scheduler.pick_new_problem(conn, user_id)
            if problem is None:
                console.print(
                    "[green]Every curated problem is solved — nothing new to pick. "
                    "Run `dojo warmup` to keep patterns alive.[/green]"
                )
                _print_footer(console, conn, user_id)
                return 0
            slug = problem["slug"]
            console.print(
                f"[bold]Scheduler pick:[/bold] {problem['title']} "
                f"({problem['pattern']}, {problem['difficulty']}) — weakest pattern first."
            )
        outcome = run_day(conn, console, backend, slug, user, open_editor=args.open)
        _print_footer(console, conn, user_id)
    return 0 if outcome in ("solved", "quit", "warmup_done") else 1


def _cmd_warmup(args) -> int:
    from dojo.session import run_warmups
    from dojo.tutor import get_backend

    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        try:
            backend = get_backend()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        run_warmups(conn, console, backend, user, limit=3)
    return 0


def _cmd_check(args) -> int:
    from dojo.session import run_check

    console = Console()
    slug = args.slug
    if slug is None:
        from dojo.config import WORKBENCH_DIR

        state_files = sorted(WORKBENCH_DIR.glob("*.state.json")) if WORKBENCH_DIR.exists() else []
        if state_files:
            slug = state_files[0].stem.removesuffix(".state")
        if slug is None:
            console.print("[red]No active session. Start with `dojo day <slug>`.[/red]")
            return 1
    with connect(DB_PATH) as conn:
        outcome = run_check(conn, console, slug)
    return 0 if outcome == "ok" else 1


def _cmd_profile(args) -> int:
    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT p.slug, p.title, p.difficulty, a.status, a.hint_count,
                   a.self_reported_time, a.measured_time_class, a.measured_time_r2,
                   a.self_reported_space, a.measured_space_class, a.submitted_at
            FROM attempts a JOIN problems p ON p.id = a.problem_id
            WHERE a.user_id = (SELECT id FROM users WHERE name = ?)
            ORDER BY a.id
            """,
            (user,),
        ).fetchall()
    table = Table(title=f"Attempts — {user}")
    for col in (
        "Problem", "Difficulty", "Status", "Hints", "Claimed time", "Measured time",
        "r²", "Claimed space", "Measured space", "Submitted",
    ):
        table.add_column(col)
    for r in rows:
        table.add_row(
            f"{r['title']} [dim]({r['slug']})[/dim]",
            r["difficulty"],
            r["status"],
            str(r["hint_count"]),
            r["self_reported_time"] or "—",
            r["measured_time_class"] or "—",
            str(r["measured_time_r2"]) if r["measured_time_r2"] is not None else "—",
            r["self_reported_space"] or "—",
            r["measured_space_class"] or "—",
            r["submitted_at"] or "—",
        )
    console.print(table)
    return 0


def _cmd_history(args) -> int:
    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        user_id = get_or_create_user(conn, user)
        rows = list_attempts(conn, user_id, slug=args.slug, limit=args.limit)
    table = Table(title=f"Attempts — {user}")
    for col in (
        "id", "problem", "kind", "status", "hints",
        "claimed", "measured", "r²", "submitted",
    ):
        table.add_column(col)
    for r in rows:
        claimed = " / ".join(
            x for x in (r["self_reported_time"], r["self_reported_space"]) if x
        )
        table.add_row(
            str(r["id"]),
            f"{r['title']} [dim]({r['slug']})[/dim]",
            r["kind"],
            r["status"],
            str(r["hint_count"]),
            (claimed or "—")[:40],
            r["measured_time_class"] or "—",
            str(r["measured_time_r2"]) if r["measured_time_r2"] is not None else "—",
            (r["submitted_at"] or r["started_at"])[:19],
        )
    console.print(table)
    if rows:
        console.print(
            "[dim]`dojo show <id>` for the full attempt: hints, code, review, "
            "reflection.[/dim]"
        )
    else:
        console.print("[dim]No attempts yet — solve something with `dojo day`.[/dim]")
    return 0


def _measured_cell(row, axis: str) -> str:
    cls = row[f"measured_{axis}_class"]
    if not cls:
        return "—"
    r2 = row[f"measured_{axis}_r2"]
    return f"{cls} (r²={round(r2, 3)})" if r2 is not None else cls


def _format_review(review: dict) -> str:
    from dojo.tutor import de_markdown

    lines = []
    for dim in (
        "correctness",
        "approach_quality",
        "style_idiom",
        "naming",
        "edge_cases",
        "complexity_claim_check",
    ):
        entry = review.get(dim, {})
        if isinstance(entry, dict):
            lines.append(
                f"{dim.replace('_', ' ')}: {entry.get('score', '?')}/5 — "
                f"{de_markdown(str(entry.get('comment', '')))}"
            )
    if review.get("broader_picture"):
        lines.append("")
        lines.append(f"Broader picture: {de_markdown(str(review['broader_picture']))}")
    if review.get("overall_comment"):
        lines.append("")
        lines.append(f"Overall: {de_markdown(str(review['overall_comment']))}")
    return "\n".join(lines)


def _cmd_show(args) -> int:
    from dojo.tutor import de_markdown

    console = Console()
    with connect(DB_PATH) as conn:
        row = get_attempt(conn, args.attempt_id)
    if row is None:
        console.print(
            f"[red]No attempt with id {args.attempt_id}. Try `dojo history`.[/red]"
        )
        return 1
    if args.code:
        console.print(row["code"] or "(no code recorded)")
        return 0

    console.print(
        Panel(
            f"[bold]{row['title']}[/bold] [{row['difficulty']}] — "
            f"{row['pattern']}\n\n{row['statement']}",
            title=f"Attempt {row['id']} — {row['kind']}",
        )
    )
    console.print(
        f"[dim]status: {row['status']} · started: {row['started_at']} · "
        f"submitted: {row['submitted_at'] or '—'} · "
        f"duration: {row['duration_seconds'] or '—'}s · "
        f"hints: {row['hint_count']}[/dim]"
    )
    table = Table(title="Complexity: claimed vs. measured")
    table.add_column("")
    table.add_column("You claimed")
    table.add_column("Measured")
    table.add_row("Time", row["self_reported_time"] or "—", _measured_cell(row, "time"))
    table.add_row("Space", row["self_reported_space"] or "—", _measured_cell(row, "space"))
    console.print(table)

    hints = loads_json(row["hints"], [])
    if hints:
        hint_table = Table(title="Hint transcript")
        hint_table.add_column("tier")
        hint_table.add_column("you asked")
        hint_table.add_column("tutor said")
        for h in hints:
            hint_table.add_row(
                str(h.get("tier", "?")),
                de_markdown(str(h.get("user", ""))),
                de_markdown(str(h.get("hint", ""))),
            )
        console.print(hint_table)
    if row["code"]:
        console.print(Panel(row["code"], title="Code", border_style="blue"))
    analysis = loads_json(row["static_analysis"], {})
    if analysis:
        findings = []
        for entry in analysis.get("complexity", []):
            findings.append(
                f"{entry['name']}: complexity {entry['complexity']} "
                f"(rank {entry.get('rank', '?')})"
            )
        for finding in analysis.get("ruff", []):
            findings.append(
                f"ruff {finding['code']} line {finding['line']}: {finding['message']}"
            )
        if findings:
            console.print(
                Panel("\n".join(findings), title="Static analysis", border_style="magenta")
            )
    review = loads_json(row["review"], {})
    if review:
        console.print(Panel(_format_review(review), title="AI review", border_style="green"))
    if row["reflection"]:
        console.print(Panel(row["reflection"], title="Reflection", border_style="cyan"))
    return 0


def _cmd_curate(args) -> int:
    import json

    from dojo.config import REPO_ROOT
    from dojo.curator import CuratorError, apply, curate_dual
    from dojo.tutor import get_backend

    console = Console()
    if args.file:
        statement = Path(args.file).read_text()
    elif args.text:
        statement = args.text
    else:
        console.print("[dim]Paste the problem statement, then Ctrl-D:[/dim]")
        statement = sys.stdin.read()
    if not statement.strip():
        console.print("[red]No statement provided.[/red]")
        return 1
    try:
        backend = get_backend()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    try:
        proposal = curate_dual(backend, statement)
    except CuratorError as exc:
        console.print(f"[red]Curation proposal rejected: {exc}[/red]")
        return 1
    # Provenance record (gitignored scratch).
    proposal_dir = REPO_ROOT / "data" / "curation"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    (proposal_dir / f"{proposal['slug']}.proposal.json").write_text(
        json.dumps(proposal, indent=2)
    )
    try:
        summary = apply(proposal)
    except CuratorError as exc:
        console.print(f"[red]Curation failed and was rolled back: {exc}[/red]")
        return 1
    console.print(
        f"[green]Curated {summary['slug']} "
        f"({summary['pattern']}, {summary['difficulty']}).[/green]\n"
        f"Wrote {summary['problem_file']}, registry entries, and the overrides "
        f"entry; verification gate passed.\n[dim]{summary['verification']}[/dim]"
    )
    return 0


def _cmd_fetch(args) -> int:
    """v0.3: fetch a LeetCode problem, land its statement in the bank, then
    auto-curate it (statement stays if curation fails or no backend)."""
    import json

    from dojo.config import REPO_ROOT
    from dojo.curator import CuratorError, apply, curate_dual
    from dojo.fetcher import LeetCodeError, fetch_problem, land
    from dojo.tutor import get_backend

    console = Console()
    try:
        problem = fetch_problem(args.title_slug)
    except LeetCodeError as exc:
        console.print(f"[red]Fetch failed: {exc}[/red]")
        return 1
    try:
        path = land(problem, problems_dir=PROBLEMS_DIR, db_path=DB_PATH)
    except LeetCodeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    console.print(
        f"[green]Landed {problem.title} ({problem.title_slug}) — "
        f"{problem.pattern}, {problem.difficulty}.[/green]\n{path}"
    )
    try:
        backend = get_backend()
    except RuntimeError as exc:
        console.print(
            f"[yellow]Statement landed uncurated — no AI backend ({exc}). "
            "Curate later with `dojo curate --file <path>`.[/yellow]"
        )
        return 0
    hints = {"pattern": problem.pattern}
    if problem.function_name:
        hints["function_name"] = problem.function_name
    if problem.signature:
        hints["signature"] = json.dumps(problem.signature)
    try:
        proposal = curate_dual(backend, problem.statement, hints)
    except CuratorError as exc:
        console.print(
            f"[yellow]Statement landed, but the curator proposal was "
            f"rejected: {exc}[/yellow]"
        )
        return 1
    proposal_dir = REPO_ROOT / "data" / "curation"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    (proposal_dir / f"{proposal['slug']}.proposal.json").write_text(
        json.dumps(proposal, indent=2)
    )
    try:
        summary = apply(proposal)
    except CuratorError as exc:
        console.print(
            f"[red]Curation failed and was rolled back; the statement stays "
            f"in the bank uncurated: {exc}[/red]"
        )
        return 1
    console.print(
        f"[green]Curated {summary['slug']} — verification gate passed.[/green]"
    )
    return 0


def _cmd_progress(args) -> int:
    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        user_id = get_or_create_user(conn, user)
        attempt_rows = conn.execute(
            """
            SELECT p.pattern AS pattern,
                   SUM(CASE WHEN a.status = 'correct' THEN 1 ELSE 0 END) AS solved,
                   COUNT(a.id) AS attempts,
                   ROUND(AVG(a.hint_count), 1) AS avg_hints
            FROM attempts a JOIN problems p ON p.id = a.problem_id
            WHERE a.user_id = ? AND p.pattern IS NOT NULL
            GROUP BY p.pattern
            """,
            (user_id,),
        ).fetchall()
        card_rows = {
            r["pattern"]: r
            for r in conn.execute(
                """
                SELECT pattern,
                       COUNT(*) AS cards,
                       SUM(CASE WHEN due_at <= ? THEN 1 ELSE 0 END) AS due,
                       ROUND(AVG(stability), 2) AS avg_stability,
                       ROUND(AVG(difficulty), 1) AS avg_difficulty
                FROM pattern_cards WHERE user_id = ? GROUP BY pattern
                """,
                (now(), user_id),
            ).fetchall()
        }
        trends = review_trends(conn, user_id)
    patterns = sorted({r["pattern"] for r in attempt_rows} | set(card_rows))
    table = Table(title=f"Pattern proficiency — {user}")
    for col in ("pattern", "solved", "attempts", "avg hints", "cards", "due now", "avg stability", "avg difficulty"):
        table.add_column(col)
    for pattern in patterns:
        a = next((r for r in attempt_rows if r["pattern"] == pattern), None)
        c = card_rows.get(pattern)
        table.add_row(
            pattern,
            str(a["solved"]) if a else "0",
            str(a["attempts"]) if a else "0",
            str(a["avg_hints"]) if a and a["avg_hints"] is not None else "—",
            str(c["cards"]) if c else "0",
            str(c["due"]) if c else "0",
            str(c["avg_stability"]) if c else "—",
            str(c["avg_difficulty"]) if c else "—",
        )
    console.print(table)
    console.print(
        "[dim]Stability = FSRS-lite memory strength in days; the scheduler picks "
        "new problems from the weakest pattern (lowest avg stability).[/dim]"
    )
    if trends:
        t = Table(title="Score trends per pattern (review rubric, recency-weighted)")
        for col in (
            "pattern", "solves", "corr", "appr", "styl", "name", "edge", "comp", "overall",
        ):
            t.add_column(col)
        for r in trends:
            d = r["dims"]
            t.add_row(
                r["pattern"],
                str(r["solves"]),
                str(d["correctness"]),
                str(d["approach_quality"]),
                str(d["style_idiom"]),
                str(d["naming"]),
                str(d["edge_cases"]),
                str(d["complexity_claim_check"]),
                str(r["overall"]),
            )
        console.print(t)
        console.print(
            "[dim]Scores come from the AI reviewer's rubric; the newest "
            "attempts weigh most.[/dim]"
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dojo", description="AI-guided interview prep: never-solve tutor + empirical grader."
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="list the problem bank")
    p_list.add_argument("--pattern", help="filter by pattern directory")
    p_list.set_defaults(func=_cmd_list)

    p_day = sub.add_parser("day", help="the daily routine (bare `dojo` runs this)")
    p_day.add_argument("slug", nargs="?", help="problem slug (scheduler picks if omitted)")
    p_day.add_argument("--open", action="store_true", help="open $EDITOR right away (use the in-session `open` command instead)")
    p_day.add_argument("--skip-warmup", action="store_true", help="skip due warm-up retrievals")
    p_day.set_defaults(func=_cmd_day)

    p_warmup = sub.add_parser("warmup", help="run due warm-up retrievals only")
    p_warmup.set_defaults(func=_cmd_warmup)

    p_check = sub.add_parser("check", help="run visible tests on the active workbench")
    p_check.add_argument("slug", nargs="?", help="problem slug (default: active session)")
    p_check.set_defaults(func=_cmd_check)

    p_profile = sub.add_parser("profile", help="show attempt history")
    p_profile.set_defaults(func=_cmd_profile)

    p_history = sub.add_parser("history", help="list your attempts, newest first")
    p_history.add_argument("--slug", help="filter to one problem")
    p_history.add_argument("--limit", type=int, help="show only the last N attempts")
    p_history.set_defaults(func=_cmd_history)

    p_show = sub.add_parser("show", help="full detail of one attempt")
    p_show.add_argument("attempt_id", type=int, help="attempt id from `dojo history`")
    p_show.add_argument(
        "--code", action="store_true", help="print only the submitted code"
    )
    p_show.set_defaults(func=_cmd_show)

    p_progress = sub.add_parser("progress", help="per-pattern proficiency + card schedule")
    p_progress.set_defaults(func=_cmd_progress)

    p_user = sub.add_parser("user", help="switch the active user (numbered picker without a name)")
    p_user.add_argument("name", nargs="?", help="the user to switch to")
    p_user.set_defaults(func=_cmd_user)

    p_setup = sub.add_parser("setup", help="re-run the setup wizard (key, user, PATH)")
    p_setup.add_argument("--user", help="register this user without prompting")
    p_setup.add_argument("--skip-key", action="store_true", help="don't prompt for an API key")
    p_setup.add_argument("--no-path", action="store_true", help="don't offer the PATH install")
    p_setup.set_defaults(func=_cmd_setup)

    p_curate = sub.add_parser("curate", help="AI-curate a new problem from a statement")
    p_curate.add_argument(
        "--text", help="the problem statement (alternative: stdin or --file)"
    )
    p_curate.add_argument("--file", help="read the statement from a file")
    p_curate.set_defaults(func=_cmd_curate)

    p_fetch = sub.add_parser("fetch", help="fetch a LeetCode problem and auto-curate it")
    p_fetch.add_argument(
        "title_slug", help="LeetCode problem slug (URL path), e.g. two-sum"
    )
    p_fetch.set_defaults(func=_cmd_fetch)
    return parser


PARSER = _build_parser()
COMMANDS = set(PARSER._subparsers._group_actions[0].choices)  # noqa: SLF001
USER_COMMANDS = {"day", "warmup", "profile", "history", "progress", "list"}


def _resolve_for_dispatch(args, console: Console):
    """Attach args._user, running the setup wizard on first run. Returns the
    user name or None (dispatch prints guidance and exits 1)."""
    from dojo.setup import default_user_name, run_wizard

    conf = load_conf()
    with connect(DB_PATH) as conn:
        try:
            return _active_user(conn, conf.get("user"))
        except NeedsSetup:
            if not sys.stdin.isatty():
                console.print(
                    "[red]First run — no user yet. Run `dojo setup` "
                    "interactively, or `dojo setup --user NAME --skip-key --no-path` "
                    "for a scripted install.[/red]"
                )
                return None
            console.print("[yellow]Welcome to dojo — one-time setup first.[/yellow]")
            try:
                run_wizard(
                    console,
                    dotenv_path=REPO_ROOT / ".env",
                    conf_path=REPO_ROOT / "data" / "dojo.conf",
                    db_path=DB_PATH,
                    problems_dir=PROBLEMS_DIR,
                    default_name=default_user_name(
                        os.environ.get("USER"), _git_user_name()
                    ),
                    key_getter=lambda: getpass.getpass(
                        "DeepSeek API key (Enter to skip): "
                    ),
                    path_install=_make_path_installer(console),
                )
            except Exception as exc:  # noqa: BLE001 - surface, then exit cleanly
                console.print(f"[red]Setup failed: {exc}[/red]")
                return None
            conf = load_conf()
            return _active_user(conn, conf.get("user"))
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return None


def _git_user_name() -> str | None:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, timeout=5
        )
        return proc.stdout.strip() or None
    except Exception:  # noqa: BLE001 - git may be absent; the default just degrades
        return None


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    argv = _normalize_argv(raw, COMMANDS)
    args = PARSER.parse_args(argv)
    if args.command is None:
        PARSER.print_help()
        return 0
    console = Console()
    if args.command != "setup":
        ensure_seeded(DB_PATH)
    if args.command in USER_COMMANDS:
        args._user = _resolve_for_dispatch(args, console)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
