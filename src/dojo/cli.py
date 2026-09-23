"""The dojo CLI.

  dojo                        the daily routine (warm-ups + a picked problem)
  dojo <slug>                 the daily routine on a specific problem
  dojo day [SLUG]             the same, explicitly (alias)
  dojo warmup                 run due warm-up retrievals only
  dojo learn [TOPIC]          learning mode: a topic primer with a practice handoff
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
from dojo.config import (
    CURATION_DIR,
    DB_PATH,
    DOJO_CONF,
    PROBLEMS_DIR,
    REPO_ROOT,
    WORKBENCH_DIR,
    load_conf,
    save_conf,
)
from dojo.db import (
    connect,
    get_attempt,
    get_revision,
    list_revisions,
    get_or_create_user,
    list_attempts,
    loads_json,
    now,
    review_trends,
    unstudied,
)
from dojo.patterns import PATTERNS
from dojo.terminal import make_prompt
from dojo.ui import table as ui_table
from dojo.version import VERSION


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


def _choose(console: Console, title: str, options: list[str]) -> str | None:
    """The shared numbered picker (v0.8 — generalized from the user picker
    to serve `dojo learn` too): returns the chosen option, or None on 'q'."""
    while True:
        console.print(f"{title}:")
        for i, name in enumerate(options, start=1):
            console.print(f"  {i}. {name}")
        raw = make_prompt(console)("Pick a number (q to cancel): ").strip()
        if raw.lower() == "q":
            return None
        try:
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1]
        except ValueError:
            pass
        console.print("[red]Not a valid choice — try again.[/red]")


def _choose_user(console: Console, names: list[str]) -> str | None:
    """The `dojo user` numbered picker: returns the chosen name, or None on
    'q'."""
    return _choose(console, "Users", names)


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
        answer = make_prompt(console)("Install? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            return False
        install_wrapper(bin_dir, str(REPO_ROOT))
        if str(bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
            shell = os.path.basename(os.environ.get("SHELL", ""))
            rc_name = ".zshrc" if "zsh" in shell else ".bashrc"
            rc_path = Path(os.path.expanduser("~")) / rc_name
            line = rc_line(str(bin_dir))
            if (
                make_prompt(console)(
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
        conf_path=DOJO_CONF,
        db_path=DB_PATH,
        problems_dir=PROBLEMS_DIR,
        default_name=default_user_name(os.environ.get("USER"), _git_user_name()),
        user_override=args.user,
        key_getter=(lambda: "")
        if args.skip_key
        else (lambda: getpass.getpass("DeepSeek API key (Enter to skip): ")),
        detect_env_key=not args.skip_key,
        path_install=None if args.no_path else _make_path_installer(console),
        provider_override=getattr(args, "provider", None),
    )
    return 0


def _cmd_update(args) -> int:
    """Pull the latest dojo and refresh dependencies (v0.10.1). The same
    fast-forward runs automatically on every other CLI entry."""
    from dojo.updater import update_dojo

    console = Console()
    console.print(update_dojo(console, force=args.force))
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
    table = ui_table("Problem bank")
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


def _roadmap_rows(conn, user_id):
    """The roadmap view's data (v0.10): one row per group — ladder size,
    what's in the bank, what's solved, and the gate state (complete / next
    up / locked-by). Pure query logic; `_cmd_roadmap` renders it."""
    from dojo import scheduler
    from dojo.patterns import prereqs_of
    from dojo.roadmap import load_roadmap, next_ladder_problem

    groups = load_roadmap()
    solved, bank = scheduler.ladder_state(conn, user_id)
    next_pick = scheduler.pick_new_problem(conn, user_id)
    rows = []
    for group in groups:
        pattern = group["slug"]
        available = [lc for lc in group["problems"] if lc in bank]
        done = sum(1 for lc in available if lc in solved)
        locked_by = None
        for prereq in prereqs_of(pattern):
            if next_ladder_problem(groups, prereq, solved, bank) is not None:
                locked_by = prereq
                break
        rows.append(
            {
                "pattern": pattern,
                "ladder": len(group["problems"]),
                "available": len(available),
                "solved": done,
                "complete": bool(available) and done == len(available),
                "next_up": next_pick is not None and next_pick["pattern"] == pattern,
                "locked_by": locked_by,
            }
        )
    return rows, next_pick


def _roadmap_problem_map(conn):
    """lc -> (title, curated) for every ladder problem in the bank."""
    rows = conn.execute(
        """
        SELECT lc_number, title, function_name, visible_tests FROM problems
        WHERE lc_number IS NOT NULL
        """
    ).fetchall()
    return {
        r["lc_number"]: (r["title"], bool(r["function_name"] and r["visible_tests"]))
        for r in rows
    }


def _roadmap_tree(conn, user_id):
    """The tree view's data (v0.10.9): the per-group rows from
    _roadmap_rows plus each group's ladder as per-problem entries with a
    state — solved / next (the ladder's earliest unsolved in this group)
    / ready (curated in bank) / missing (not fetched). Pure queries;
    the renderer draws it."""
    from dojo import scheduler
    from dojo.roadmap import load_roadmap, next_ladder_problem

    groups = load_roadmap()
    solved, bank = scheduler.ladder_state(conn, user_id)
    problem_map = _roadmap_problem_map(conn)
    next_pick = scheduler.pick_new_problem(conn, user_id)
    rows, _ = _roadmap_rows(conn, user_id)

    entries = []
    for group, row in zip(groups, rows):
        next_lc = next_ladder_problem(groups, group["slug"], solved, bank)
        problems = []
        for lc in group["problems"]:
            title, curated = problem_map.get(lc, (None, False))
            if lc in solved:
                state = "solved"
            elif lc == next_lc and curated:
                state = "next"
            elif curated:
                state = "ready"
            else:
                state = "missing"
            problems.append(
                {"lc": lc, "state": state, "title": title or f"problem {lc}"}
            )
        entries.append({**row, "slug": group["slug"], "problems": problems})
    return entries, next_pick


def _render_roadmap_tree(console, entries, next_pick, expand=None, expand_all=False):
    """The tree view (v0.10.9): groups as branches (the prereq chain is
    the skeleton), each group's ladder as leaves with ✓/→/○/· markers.
    The next-up group expands by default; --expand/--all open more."""
    from rich.tree import Tree

    tree = Tree("NeetCode 150 — your progress")
    expand_set = set(expand or [])
    for entry in entries:
        slug = entry["slug"]
        if entry["complete"]:
            status = f"[green]✓ {entry['solved']}/{entry['available']}[/green]"
        elif entry["next_up"]:
            status = f"[cyan]→ {entry['solved']}/{entry['available']}[/cyan]  ← next up"
        elif entry["locked_by"]:
            status = (
                f"[dim]🔒 {entry['solved']}/{entry['available']}[/dim] "
                f"(finish {entry['locked_by']})"
            )
        else:
            status = f"{entry['solved']}/{entry['available']}"
        node = tree.add(f"{slug}  {status}")
        if not (expand_all or entry["next_up"] or slug in expand_set):
            continue
        for problem in entry["problems"]:
            if problem["state"] == "solved":
                node.add(f"[green]✓[/green] {problem['lc']} {problem['title']}")
            elif problem["state"] == "next":
                node.add(f"[cyan]→ {problem['lc']} {problem['title']}[/cyan]")
            elif problem["state"] == "ready":
                node.add(f"○ {problem['lc']} {problem['title']}")
            else:
                node.add(f"[dim]· {problem['lc']} {problem['title']}[/dim]")
    console.print(tree)
    if next_pick is not None:
        console.print(
            f"[bold]Next up:[/bold] {next_pick['title']} "
            f"[dim]({next_pick['pattern']})[/dim] — run `dojo` to start it."
        )
    else:
        console.print(
            "[green]Every ladder problem in the bank is solved — `dojo` "
            "now serves dojo's own problems.[/green]"
        )


def _cmd_roadmap(args) -> int:
    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        user_id = get_or_create_user(conn, user)
        if not args.table:
            entries, next_pick = _roadmap_tree(conn, user_id)
            _render_roadmap_tree(
                console, entries, next_pick, expand=args.expand, expand_all=args.all
            )
            return 0
        rows, next_pick = _roadmap_rows(conn, user_id)

        table = ui_table("The roadmap — NeetCode 150 progression")
        table.add_column("Pattern")
        table.add_column("Solved")
        table.add_column("In bank")
        table.add_column("Ladder")
        table.add_column("Status")
        for row in rows:
            status = ""
            if row["complete"]:
                status = "[green]✓ complete[/green]"
            elif row["next_up"]:
                status = "[cyan]→ next up[/cyan]"
            elif row["locked_by"]:
                status = f"[dim]locked — finish {row['locked_by']}[/dim]"
            else:
                status = "[dim]—[/dim]"
            table.add_row(
                row["pattern"],
                f"{row['solved']}/{row['available']}",
                str(row["available"]),
                str(row["ladder"]),
                status,
            )
        console.print(table)
        if next_pick is not None:
            console.print(
                f"[bold]Next up:[/bold] {next_pick['title']} "
                f"[dim]({next_pick['pattern']})[/dim] — run `dojo` to start it."
            )
        else:
            console.print(
                "[green]Every ladder problem in the bank is solved — `dojo` "
                "now serves dojo's own problems.[/green]"
            )
    return 0


def _print_footer(console: Console, conn, user_id: int) -> None:
    # "next warm-up: later today at 23:48", not "tomorrow: 1 card(s) due" — the
    # old line counted a rolling 24 hours and called it tomorrow, so a card due
    # tonight was announced as tomorrow's (v0.13 follow-up).
    parts = [scheduler.due_summary(conn, user_id)]
    trends = review_trends(conn, user_id)
    if trends:
        best = max(trends, key=lambda t: t["overall"])
        parts.append(f"best pattern: {best['pattern']} ({best['overall']})")
    console.print("[dim]" + " · ".join(parts) + "[/dim]")


def _run_practice_session(conn, console, backend, user, slug, open_editor=False) -> str:
    """Run solve sessions, looping while the in-session `learn` handoff keeps
    sending us back ("practice" — v0.8). Shared by `dojo day` and the
    `dojo learn` handoff; a warm-up never reaches this loop."""
    from dojo.session import run_day

    outcome = "practice"
    while outcome == "practice":
        outcome = run_day(conn, console, backend, slug, user, open_editor=open_editor)
    return outcome


def _cmd_day(args) -> int:
    from dojo.session import run_learn, run_warmups
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
        console.print(f"[dim]Status: {scheduler.due_summary(conn, user_id)}.[/dim]")
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
                f"({problem['pattern']}, {problem['difficulty']}) — roadmap order, prerequisites gated."
            )
            # The proactive learn offer (v0.8): only for scheduler picks
            # (explicit slugs are deliberate choices), only for unstudied
            # patterns, and a fork, never a gate — either way the session
            # proceeds.
            if unstudied(conn, user_id, problem["pattern"]):
                answer = make_prompt(console)(
                    f"This is from '{problem['pattern']}' — a pattern you haven't "
                    "studied yet. Learn it first? [y/N] "
                ).strip().lower()
                if answer in ("y", "yes"):
                    result = run_learn(
                        conn, console, backend, user, problem["pattern"], handoff_slug=slug
                    )
                    if result.get("practice"):
                        slug = result["practice"]
                        console.print(
                            f"[dim]Retrying '{slug}' with a fresh template.[/dim]"
                        )
        outcome = _run_practice_session(
            conn, console, backend, user, slug, open_editor=args.open
        )
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
        run_warmups(conn, console, backend, user, limit=max(1, args.limit))
    return 0


def _cmd_learn(args) -> int:
    """v0.8 learning mode: a topic primer conversation with a practice
    handoff. No topic → the shared numbered picker; an unknown topic gets a
    did-you-mean suggestion, never a silent wrong pattern."""
    from dojo.session import run_learn
    from dojo.session.learn import resolve_pattern
    from dojo.tutor import get_backend

    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    if args.topic is None:
        pattern = _choose(console, "Topics", list(PATTERNS))
        if pattern is None:
            return 0
    else:
        pattern, suggestion = resolve_pattern(args.topic)
        if pattern is None:
            if suggestion:
                console.print(
                    f"[red]Unknown pattern '{args.topic}' — did you mean "
                    f"'{suggestion}'?[/red]"
                )
            else:
                console.print(
                    f"[red]Unknown pattern '{args.topic}' — `dojo learn` opens "
                    "a picker, `dojo list` shows the bank.[/red]"
                )
            return 1
    with connect(DB_PATH) as conn:
        try:
            backend = get_backend()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        result = run_learn(conn, console, backend, user, pattern)
        if result.get("practice"):
            console.print(
                f"[bold]Practice:[/bold] {result['practice']} — opening a "
                "fresh session."
            )
            outcome = _run_practice_session(
                conn, console, backend, user, result["practice"]
            )
            return 0 if outcome in ("solved", "quit") else 1
    return 0


def _active_state_slug(console: Console) -> str | None:
    """The slug of the most recently touched live session, or None.

    Choosing the alphabetically first state file (the v0.10 behaviour) meant
    `dojo check` could silently test a file the student is not looking at as soon
    as a second crashed session existed — and crash recovery is the *only* resume
    path by design (v0.11). Also prints which session was chosen, so the guess is
    never invisible."""
    if not WORKBENCH_DIR.exists():
        return None
    files = sorted(
        WORKBENCH_DIR.glob("*.state.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    slug = files[0].stem.removesuffix(".state")
    if len(files) > 1:
        console.print(
            f"[dim]Active session: {slug} (of {len(files)} live sessions — "
            "most recently used).[/dim]"
        )
    return slug


def _cmd_check(args) -> int:
    from dojo.session import run_check

    console = Console()
    slug = args.slug
    if slug is None:
        slug = _active_state_slug(console)
        if slug is None:
            console.print("[red]No active session. Start with `dojo day <slug>`.[/red]")
            return 1
    with connect(DB_PATH) as conn:
        outcome = run_check(conn, console, slug)
    return 0 if outcome == "ok" else 1


def _cmd_history(args) -> int:
    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        user_id = get_or_create_user(conn, user)
        rows = list_attempts(conn, user_id, slug=args.slug, limit=args.limit)
    table = ui_table(f"Attempts — {user}")
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
    """One axis of `dojo show`'s complexity table.

    v0.12: the measured side is a paired comparison, so the useful detail is the
    cost-ratio trend rather than an R² from a fit that no longer exists."""
    cls = row[f"measured_{axis}_class"]
    record = loads_json(row["measurement"], None) if "measurement" in row.keys() else None
    verdict = (record or {}).get(axis) or {}
    trend = verdict.get("trend")
    if not cls:
        if verdict.get("kind") == "failed":
            return verdict.get("note", "failed at scale")
        return "—"
    return f"{cls} (×{trend:.2f} vs reference)" if trend else cls


def _revision_table(conn, attempt_id: int) -> int:
    """`dojo show <id> --revisions`: one row per submitted version."""
    rows = list_revisions(conn, attempt_id)
    if not rows:
        print(
            f"No revisions recorded for attempt {attempt_id} — it predates v0.13 "
            "or was never submitted."
        )
        return 0
    table = ui_table(f"Revisions — attempt {attempt_id}")
    for col in ("#", "kind", "status", "claimed", "measured", "review", "when", "lines"):
        table.add_column(col)
    for row in rows:
        review = loads_json(row["review"], {}) or {}
        overall = review.get("overall_comment")
        scores = [
            v.get("score")
            for v in review.values()
            if isinstance(v, dict) and isinstance(v.get("score"), (int, float))
        ]
        mean = f"{sum(scores) / len(scores):.1f}/5" if scores else "—"
        del overall
        claimed = " / ".join(
            x for x in (row["self_reported_time"], row["self_reported_space"]) if x
        )
        measured = _measured_from_json(row["measurement"], "time")
        table.add_row(
            str(row["revision"]),
            row["kind"],
            row["status"],
            (claimed or "—")[:28],
            measured,
            mean,
            (row["created_at"] or "")[:19],
            str(len(row["code"].splitlines())),
        )
    console = Console()
    console.print(table)
    console.print(
        "[dim]`dojo show <id> --rev N` for one version, `--diff` for what changed.[/dim]"
    )
    return 0


def _measured_from_json(measurement_json: str | None, axis: str) -> str:
    """One axis of a revision's stored measurement (same vocabulary as
    `_measured_cell`, but reading the revision row's own record)."""
    record = loads_json(measurement_json, None) or {}
    verdict = record.get(axis) or {}
    cls = verdict.get("student_class")
    trend = verdict.get("trend")
    if cls:
        return f"{cls} (x{trend:.2f})" if trend else str(cls)
    if verdict.get("kind") == "failed":
        return verdict.get("note", "failed at scale")[:24]
    return "—"


def _revision_diff(conn, attempt_id: int, wanted: list[int] | None) -> int:
    """`dojo show <id> --diff [A [B]]`: what changed between two versions."""
    import difflib

    rows = list_revisions(conn, attempt_id)
    if len(rows) < 1:
        print(f"Attempt {attempt_id} has no revisions to compare.")
        return 1
    if wanted and len(wanted) >= 2:
        left, right = wanted[0], wanted[1]
    elif wanted:
        left, right = rows[max(0, rows.index(rows[-1]) - 1)]["revision"], wanted[0]
    else:
        if len(rows) < 2:
            print("Only one revision — nothing to diff yet (polish, then look again).")
            return 0
        left, right = rows[-2]["revision"], rows[-1]["revision"]
    by_number = {r["revision"]: r for r in rows}
    if left not in by_number or right not in by_number:
        print(f"No such revision(s): {left}, {right}. `--revisions` lists them.")
        return 1
    before = by_number[left]["code"].splitlines(keepends=True)
    after = by_number[right]["code"].splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"attempt {attempt_id} revision {left}",
            tofile=f"attempt {attempt_id} revision {right}",
            n=3,
        )
    )
    if not diff:
        print(f"Revisions {left} and {right} are identical.")
        return 0
    console = Console()
    for line in diff:
        stripped = line.rstrip("\n")
        style = ""
        if stripped.startswith("+++") or stripped.startswith("---"):
            style = "bold"
        elif stripped.startswith("+"):
            style = "green"
        elif stripped.startswith("-"):
            style = "red"
        elif stripped.startswith("@@"):
            style = "cyan"
        console.print(f"[{style}]{stripped}[/{style}]" if style else stripped)
    return 0


def _cmd_show(args) -> int:
    from dojo.render import md_plain, render_ai

    console = Console()
    with connect(DB_PATH) as conn:
        row = get_attempt(conn, args.attempt_id)
    if row is None:
        console.print(
            f"[red]No attempt with id {args.attempt_id}. Try `dojo history`.[/red]"
        )
        return 1
    with connect(DB_PATH) as conn:
        if getattr(args, "revisions", False):
            return _revision_table(conn, args.attempt_id)
        if getattr(args, "diff", None) is not None:
            return _revision_diff(conn, args.attempt_id, args.diff)
        if getattr(args, "rev", None) is not None:
            revision = get_revision(conn, args.attempt_id, args.rev)
            if revision is None:
                console.print(
                    f"[red]Attempt {args.attempt_id} has no revision {args.rev}.[/red]"
                )
                return 1
            code = revision["code"]
            if getattr(args, "clean", False):
                from dojo.session.workbench import student_view

                code = student_view(code, row) or "(nothing left after dojo's scaffolding)"
            console.print(code)
            console.print(
                f"[dim]revision {revision['revision']} of {args.attempt_id} · "
                f"{revision['kind']} · {revision['status']} · "
                f"{revision['created_at'][:19]}[/dim]"
            )
            return 0
    if args.code or getattr(args, "clean", False):
        code = row["code"] or "(no code recorded)"
        if getattr(args, "clean", False) and row["code"]:
            from dojo.session.workbench import student_view

            code = student_view(code, row) or "(no code after removing scaffolding)"
        console.print(code)
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
        f"hints: {row['hint_count']} · polished: {row['polished'] or 0}x"
        # v0.11: the recall grade is persisted on the attempt, so show it —
        # it used to be folded into the card and thrown away.
        + (
            f" · recall grade: {row['recall_grade']}"
            if row["recall_grade"] is not None
            else ""
        )
        + "[/dim]"
    )
    table = ui_table("Complexity: claimed vs. measured")
    table.add_column("")
    table.add_column("You claimed")
    table.add_column("Measured")
    table.add_row("Time", row["self_reported_time"] or "—", _measured_cell(row, "time"))
    table.add_row("Space", row["self_reported_space"] or "—", _measured_cell(row, "space"))
    console.print(table)

    # v0.12: what the scale probe found is often the most important thing on the
    # row — a crash or an output disagreement at a size the judge never reaches.
    record = loads_json(row["measurement"], None) if "measurement" in row.keys() else None
    if record:
        if record.get("failure"):
            where = record.get("failed_at")
            console.print(
                f"[red]scale probe: failed at n={where:,}: {record['failure']}[/red]"
                if where
                else f"[red]scale probe: {record['failure']}[/red]"
            )
        if record.get("mismatch_at"):
            confirmed = " (oracle-confirmed)" if record.get("mismatch_confirmed") else ""
            console.print(
                f"[red]scale probe: output differs from the reference at "
                f"n={record['mismatch_at']:,}{confirmed}[/red]"
            )
        if not record.get("reference_used"):
            console.print(
                "[dim]scale probe: no reference registered for this problem, so "
                "growth was not compared.[/dim]"
            )

    with connect(DB_PATH) as conn:
        revisions = list_revisions(conn, args.attempt_id)
    if len(revisions) > 1:
        console.print(
            f"[dim]{len(revisions)} revisions — `dojo show {args.attempt_id} "
            "--revisions` lists them, `--diff` shows what changed.[/dim]"
        )

    hints = loads_json(row["hints"], [])
    if hints:
        hint_table = ui_table("Hint transcript")
        hint_table.add_column("tier")
        hint_table.add_column("you asked")
        hint_table.add_column("tutor said")
        for h in hints:
            hint_table.add_row(
                str(h.get("tier", "?")),
                md_plain(str(h.get("user", ""))),
                md_plain(str(h.get("hint", ""))),
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
        from dojo.render import review_markdown

        render_ai(console, "AI review", review_markdown(review), border_style="green")
    if row["reflection"]:
        console.print(Panel(row["reflection"], title="Reflection", border_style="cyan"))
    discussion = loads_json(row["discussion"], [])
    if discussion:
        for entry in discussion:
            console.print(f"[bold]you:[/bold] {entry.get('user', '')}")
            render_ai(console, "tutor", str(entry.get("tutor", "")), border_style="green")
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
    proposal_dir = CURATION_DIR
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


def _roadmap_entries() -> list[tuple[int, str]]:
    """(lc number, LeetCode title-slug) for every ladder problem, in
    roadmap order — built from the raw TOML entries ('0121_...')."""
    from dojo.roadmap import load_roadmap

    out = []
    for group in load_roadmap():
        for entry in group["entries"]:
            number, _, slug = entry.partition("_")
            out.append((int(number), slug.replace("_", "-")))
    return out


def _roadmap_lc_for_slug(title_slug: str) -> int | None:
    """The LeetCode number for a title-slug, per the roadmap data."""
    for lc, slug in _roadmap_entries():
        if slug == title_slug:
            return lc
    return None


def _tag_lc_number(conn, title_slug: str, lc: int | None) -> None:
    """Record the LeetCode number on a landed problem row so the roadmap
    ladder can see it (the fetcher's model doesn't carry it; the TOML is
    authoritative)."""
    if lc is None:
        return
    conn.execute(
        "UPDATE problems SET lc_number = ? WHERE slug = ? AND lc_number IS NULL",
        (lc, title_slug),
    )
    conn.commit()


def _cmd_fetch_all(console, delay: float = 0.8) -> int:
    """v0.10.10: land every roadmap problem without curating, so the whole
    NeetCode 150 is available in the bank. Idempotent: problems already in
    the bank (by LeetCode number) are skipped; failures are counted and
    retried on the next run."""
    import time

    from dojo.config import DB_PATH, PROBLEMS_DIR
    from dojo.fetcher import LeetCodeError, fetch_problem, land
    from dojo.roadmap import load_roadmap

    with connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT lc_number, function_name FROM problems WHERE lc_number IS NOT NULL"
        ).fetchall()
        existing_rows = {r["lc_number"] for r in rows}
        curated_lc = {r["lc_number"] for r in rows if r["function_name"]}
    # A problem is "already in the bank" when its row exists AND either
    # its seed file exists or the row is curated (dojo's own slugs like
    # two_sum_2 differ from the LeetCode slug but own the lc number) — a
    # row whose file is missing is a lost import and gets re-fetched.
    seed_files = {p.stem for p in PROBLEMS_DIR.rglob("*.py")}
    fetched = skipped = failed = 0
    failures = []
    for lc, slug in _roadmap_entries():
        if lc in existing_rows and (slug in seed_files or lc in curated_lc):
            # The number being *somewhere* in the table is not enough: a stale
            # duplicate once owned it while the seed row for this slug had none,
            # so the bulk fetch skipped the problem forever and left a roadmap
            # problem off the ladder (LC 50/208/235, v0.13 follow-up). Re-tag by
            # slug — the update is a no-op unless this row's tag is NULL.
            if slug in seed_files:
                with connect(DB_PATH) as conn:
                    _tag_lc_number(conn, slug, lc)
            skipped += 1
            continue
        if slug in seed_files:
            # The seed file is present but the row/tag was lost (the reseed
            # once wiped tags): restore the tag locally — no fetch needed.
            with connect(DB_PATH) as conn:
                _tag_lc_number(conn, slug, lc)
            skipped += 1
            continue
        try:
            problem = fetch_problem(slug)
            land(problem, problems_dir=PROBLEMS_DIR, db_path=DB_PATH)
            with connect(DB_PATH) as conn:
                _tag_lc_number(conn, problem.title_slug, lc)
            fetched += 1
            console.print(f"[green]✓[/green] {lc} {problem.title} ({problem.pattern})")
            time.sleep(delay)  # be polite to the endpoint
        except LeetCodeError as exc:
            if "already in the bank" in str(exc):
                # The seed file exists but its row was lost (a partial
                # import): re-seed so the row comes back, tag the lc, and
                # count it as a skip rather than a failure.
                from dojo.bank import ensure_seeded

                ensure_seeded(DB_PATH)
                with connect(DB_PATH) as conn:
                    _tag_lc_number(conn, slug, lc)
                skipped += 1
                console.print(f"[dim]• {lc} {slug}: file present — row restored[/dim]")
                continue
            failed += 1
            failures.append(f"{lc} {slug}: {exc}")
            console.print(f"[red]✗[/red] {lc} {slug}: {exc}")
    console.print(
        f"[bold]Fetched {fetched}[/bold], skipped {skipped} (already in bank), "
        f"failed {failed}. Curate later: `dojo report --fix <slug>` per problem."
    )
    if failures:
        console.print("[yellow]Failures:[/yellow]")
        for failure in failures:
            console.print(f"  • {failure}")
        console.print("[dim]Re-run `dojo fetch --all` — existing problems are skipped.[/dim]")
    return 0 if not failures else 1


def _cmd_fetch(args) -> int:
    """v0.3: fetch a LeetCode problem, land its statement in the bank, then
    auto-curate it (statement stays if curation fails or no backend)."""
    import json

    from dojo.config import REPO_ROOT
    from dojo.curator import CuratorError, apply, curate_dual
    from dojo.fetcher import LeetCodeError, fetch_problem, land
    from dojo.tutor import get_backend

    console = Console()
    if args.all:
        return _cmd_fetch_all(console)
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
    with connect(DB_PATH) as conn:
        _tag_lc_number(conn, problem.title_slug, _roadmap_lc_for_slug(problem.title_slug))
    console.print(
        f"[green]Landed {problem.title} ({problem.title_slug}) — "
        f"{problem.pattern}, {problem.difficulty}.[/green]\n{path}"
    )
    if args.no_curate:
        console.print(
            "[dim]Not curated — `dojo report --fix` audits + re-curates when "
            "you're ready.[/dim]"
        )
        return 0
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
    proposal_dir = CURATION_DIR
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


def _cmd_reference(args) -> int:
    """Generate and gate the canonical reference solutions the probe measures
    against (v0.12).

    A reference is only admitted when it agrees with the brute-force oracle
    everywhere the oracle can run, so a failed generation writes nothing."""
    from dojo.curator import CuratorError, add_reference
    from dojo.judge import ORACLES, REFERENCES
    from dojo.tutor import get_backend

    console = Console()
    if not args.slug and not args.all:
        console.print("[red]Pass a slug, or --all to backfill the bank.[/red]")
        return 1
    try:
        backend = get_backend()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    with connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT slug FROM problems WHERE function_name IS NOT NULL "
            "AND visible_tests IS NOT NULL ORDER BY slug"
        ).fetchall()
    curated = [r["slug"] for r in rows]
    if args.slug:
        if args.slug not in curated:
            console.print(f"[red]'{args.slug}' is not a curated problem.[/red]")
            return 1
        targets = [args.slug]
    else:
        targets = [s for s in curated if args.force or s not in REFERENCES]

    if not targets:
        console.print("[green]Every curated problem already has a reference.[/green]")
        return 0

    written = skipped = failed = 0
    for slug in targets:
        if slug not in ORACLES:
            console.print(
                f"[yellow]• {slug}: no @oracle to gate against — skipped.[/yellow]"
            )
            skipped += 1
            continue
        try:
            summary = add_reference(slug, backend, overwrite=args.force)
        except CuratorError as exc:
            console.print(f"[yellow]• {slug}: {exc}[/yellow]")
            failed += 1
            continue
        note = f" — {summary['note']}" if summary.get("note") else ""
        console.print(f"[green]• {slug}: reference installed{note}[/green]")
        written += 1

    console.print(
        f"[dim]{written} installed · {skipped} skipped (no oracle) · {failed} refused[/dim]"
    )
    return 0 if failed == 0 else 1


def _cmd_report(args) -> int:
    import json

    from dojo.curator import CuratorError, apply, audit_curation, curate_dual
    from dojo.judge import JUDGE_CASES, ORACLES
    from dojo.tutor import get_backend

    console = Console()
    try:
        backend = get_backend()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    slug = args.slug
    with connect(DB_PATH) as conn:
        if slug is None:
            slug = _active_state_slug(console)
        if slug is None:
            console.print(
                "[red]No problem to report — pass a slug or start a session.[/red]"
            )
            return 1
        problem = conn.execute(
            "SELECT * FROM problems WHERE slug = ?", (slug,)
        ).fetchone()
    if problem is None:
        console.print(f"[red]Unknown problem '{slug}'.[/red]")
        return 1
    note = (getattr(args, "note", None) or "").strip() or None
    try:
        audit = audit_curation(
            backend,
            problem["statement"],
            loads_json(problem["visible_tests"], []),
            live_oracle=ORACLES.get(slug),
            live_generator=JUDGE_CASES.get(slug),
            note=note,
        )
    except CuratorError as exc:
        console.print(f"[red]Audit failed: {exc}[/red]")
        return 1
    report_dir = CURATION_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{slug}.report.json"
    report_path.write_text(json.dumps(audit, indent=2))
    findings = audit.get("findings") or []
    console.print(
        f"[bold]Curation audit: {slug}[/bold] — verdict: {audit.get('verdict', '?')}"
    )
    if note:
        console.print(f"[dim]Your report: {note}[/dim]")
    for finding in audit.get("automated_findings") or []:
        console.print(f"[dim]• cross-check: {finding}[/dim]")
    for finding in findings:
        console.print(f"[yellow]• {finding}[/yellow]")
    if audit.get("explanation"):
        console.print(f"[dim]{audit['explanation']}[/dim]")
    if not findings:
        console.print("[green]No contract violations found.[/green]")
    console.print(f"[dim]Report written to {report_path}[/dim]")
    if args.fix:
        if audit.get("verdict") != "fix":
            console.print("[dim]Verdict is 'ok' — skipping re-curation.[/dim]")
            return 0
        console.print("[bold]Re-curating[/bold] (dual-oracle + verification gate)...")
        try:
            proposal = curate_dual(backend, problem["statement"])
            summary = apply(proposal, overwrite=True)
        except CuratorError as exc:
            console.print(
                f"[red]Re-curation failed and was rolled back: {exc}[/red]"
            )
            return 1
        console.print(
            f"[green]Re-curated {summary['slug']} — verification gate passed.[/green]"
        )
    else:
        console.print(
            "[dim]`dojo report --fix <slug>` re-curates when the verdict is 'fix'.[/dim]"
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
                       -- `datetime()` on both sides: a raw string compare
                       -- disagreed with `due_cards` for any writer that used
                       -- SQLite's own naive `datetime('now')` form (v0.13).
                       SUM(CASE WHEN datetime(due_at) <= datetime(?) THEN 1 ELSE 0 END) AS due,
                       ROUND(AVG(stability), 2) AS avg_stability,
                       -- The weakest card is the honest signal for a pattern:
                       -- one strong problem cannot carry the others (v0.13
                       -- follow-up, per-problem cards).
                       ROUND(MIN(stability), 2) AS min_stability,
                       ROUND(AVG(difficulty), 1) AS avg_difficulty
                FROM item_cards WHERE user_id = ? GROUP BY pattern
                """,
                (now(), user_id),
            ).fetchall()
        }
        item_rows = conn.execute(
            """
            SELECT slug, pattern, stability, difficulty, reps, lapses, due_at
            FROM item_cards WHERE user_id = ? ORDER BY datetime(due_at) ASC
            """,
            (user_id,),
        ).fetchall()
        trends = review_trends(conn, user_id)
    patterns = sorted({r["pattern"] for r in attempt_rows} | set(card_rows))
    table = ui_table(f"Pattern proficiency — {user}")
    for col in ("pattern", "solved", "attempts", "avg hints", "cards", "due now",
                "avg stability", "weakest", "avg difficulty"):
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
            str(c["min_stability"]) if c else "—",
            str(c["avg_difficulty"]) if c else "—",
        )
    console.print(table)
    console.print(
        "[dim]One card per solved problem (v0.13 follow-up): `cards` counts them, "
        "`avg`/`weakest` are their stability, and the scheduler serves the coldest "
        "due card first. `dojo progress --problems` lists every card.[/dim]"
    )
    if getattr(args, "problems", False):
        items = ui_table(f"Cards — {user}")
        for col in ("problem", "pattern", "stability", "difficulty", "reps", "next review"):
            items.add_column(col)
        for r in item_rows:
            items.add_row(
                r["slug"],
                r["pattern"] or "—",
                f"{r['stability']:.2f}",
                f"{r['difficulty']:.1f}",
                str(r["reps"]),
                scheduler.due_phrase(r["due_at"]),
            )
        console.print(items)
    if trends:
        t = ui_table("Score trends per pattern (review rubric, recency-weighted)")
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


def _migrate_cards(console: Console, user: str | None) -> None:
    """Upgrade pattern cards to per-problem cards, once per user (v0.13
    follow-up). Nothing is destroyed: the rebuild is derived from the attempt
    log, and the legacy table is left untouched."""
    if not user:
        return
    from dojo import scheduler

    with connect(DB_PATH) as conn:
        user_id = get_or_create_user(conn, user)

        def note(summary: dict) -> None:
            console.print(
                f"[dim]Cards are per problem now: rebuilt {summary['cards']} from "
                f"your attempt history ({summary['recalled']} with recall, "
                f"{summary['never_recalled']} never recalled; {summary['spread']} "
                f"spread over {summary['spread_days']} days so the backlog drains "
                "at a couple a day).[/dim]"
            )

        scheduler.migrate_cards_if_needed(conn, user_id, print_note=note)


def _cmd_rebuild_cards(args) -> int:
    """`dojo rebuild-cards` (power tool): re-derive every card from the attempt
    log. The migration runs this automatically once; it stays available as the
    repair path (and to re-spread a backlog with a different window)."""
    from dojo import scheduler

    console = Console()
    user = getattr(args, "_user", None)
    if not user:
        console.print("[red]No active user — run `dojo setup`.[/red]")
        return 1
    with connect(DB_PATH) as conn:
        user_id = get_or_create_user(conn, user)
        summary = scheduler.rebuild_item_cards(
            conn, user_id, spread_days=max(0, args.spread),
            print_note=lambda s: console.print(f"[green]Rebuilt {s['cards']} card(s).[/green]"),
        )
    return 0 if summary["cards"] else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dojo",
        description="AI-guided interview prep: never-solve tutor + empirical grader.",
    )
    # pyproject.toml is the single source of truth for the version (v0.13
    # follow-up); this flag is how it becomes observable from the CLI.
    parser.add_argument(
        "--version", action="version", version=f"dojo {VERSION}"
    )
    sub = parser.add_subparsers(dest="command")

    # The visible surface is deliberately small (v0.9): bare `dojo` is the
    # daily routine, and the custom HELP_TEXT lists the commands a user
    # should actually type. Power tools stay dispatchable (`day`, `warmup`,
    # `check`, `profile`, `show`, `curate`, `report`) but never appear in
    # the top-level help — their own `dojo <cmd> --help` still documents
    # them. (argparse's help=SUPPRESS prints ==SUPPRESS== literals on 3.13,
    # so the hiding lives in the interception, not the parser.)

    p_list = sub.add_parser("list", help="the problem bank (✓ = curated, ready to solve)")
    p_list.add_argument("--pattern", help="filter by pattern directory")
    p_list.set_defaults(func=_cmd_list)

    p_day = sub.add_parser("day", help="the daily routine (bare `dojo` runs this)")
    p_day.add_argument("slug", nargs="?", help="problem slug (scheduler picks if omitted)")
    p_day.add_argument("--open", action="store_true", help="open $EDITOR right away (use the in-session `open` command instead)")
    p_day.add_argument("--skip-warmup", action="store_true", help="skip due warm-up retrievals")
    p_day.set_defaults(func=_cmd_day)

    p_warmup = sub.add_parser("warmup", help="run due warm-up retrievals only")
    p_warmup.add_argument(
        "--limit", type=int, default=3, help="how many cards to drain (default 3)"
    )
    p_warmup.set_defaults(func=_cmd_warmup)

    p_learn = sub.add_parser("learn", help="study a topic with the teacher, then practice a problem")
    p_learn.add_argument("topic", nargs="?", help="pattern to learn (picker if omitted)")
    p_learn.set_defaults(func=_cmd_learn)

    p_check = sub.add_parser("check", help="run visible tests on the active workbench")
    p_check.add_argument("slug", nargs="?", help="problem slug (default: active session)")
    p_check.set_defaults(func=_cmd_check)

    p_profile = sub.add_parser("profile", help="alias of `dojo history`")
    p_profile.set_defaults(func=_cmd_history)

    p_history = sub.add_parser("history", help="your attempts, newest first (`show <id>` for detail)")
    p_history.add_argument("--slug", help="filter to one problem")
    p_history.add_argument("--limit", type=int, help="show only the last N attempts")
    p_history.set_defaults(func=_cmd_history)

    p_show = sub.add_parser("show", help="full detail of one attempt")
    p_show.add_argument("attempt_id", type=int, help="attempt id from `dojo history`")
    p_show.add_argument(
        "--code", action="store_true", help="print only the submitted code"
    )
    p_show.add_argument(
        "--clean",
        action="store_true",
        help="print the code as the AI reads it (dojo's scaffolding removed)",
    )
    p_show.add_argument(
        "--revisions",
        action="store_true",
        help="list every version of this attempt (v0.13)",
    )
    p_show.add_argument(
        "--rev", type=int, metavar="N", help="print version N's code instead of the latest"
    )
    p_show.add_argument(
        "--diff",
        nargs="*",
        type=int,
        metavar="N",
        help="unified diff between versions (default: the last two)",
    )
    p_show.set_defaults(func=_cmd_show)

    p_progress = sub.add_parser("progress", help="per-pattern proficiency + retention schedule")
    p_progress.add_argument(
        "--problems", action="store_true", help="also list every card, coldest due first"
    )
    p_progress.set_defaults(func=_cmd_progress)

    p_roadmap = sub.add_parser("roadmap", help="the progression tree: solved, next up, locked")
    p_roadmap.add_argument(
        "--table", action="store_true", help="the stats table instead of the tree"
    )
    p_roadmap.add_argument(
        "--expand", action="append", metavar="PATTERN",
        help="also expand this pattern's ladder (repeatable)",
    )
    p_roadmap.add_argument(
        "--all", action="store_true", help="expand every pattern's ladder"
    )
    p_roadmap.set_defaults(func=_cmd_roadmap)

    p_user = sub.add_parser("user", help="switch the active user (numbered picker without a name)")
    p_user.add_argument("name", nargs="?", help="the user to switch to")
    p_user.set_defaults(func=_cmd_user)

    p_update = sub.add_parser("update", help="pull the latest dojo and refresh dependencies (auto-runs on start)")
    p_update.add_argument(
        "--force", action="store_true", help="discard local changes before pulling"
    )
    p_update.set_defaults(func=_cmd_update)

    p_setup = sub.add_parser("setup", help="re-run the setup wizard (key, name, PATH)")
    p_setup.add_argument("--user", help="register this user without prompting")
    p_setup.add_argument("--skip-key", action="store_true", help="don't prompt for an API key")
    p_setup.add_argument("--no-path", action="store_true", help="don't offer the PATH install")
    p_setup.add_argument(
        "--provider",
        choices=["deepseek", "openai", "anthropic"],
        help="use this provider's key variable (default: detect, else deepseek)",
    )
    p_setup.set_defaults(func=_cmd_setup)

    p_curate = sub.add_parser("curate", help="AI-curate a new problem from a statement")
    p_curate.add_argument(
        "--text", help="the problem statement (alternative: stdin or --file)"
    )
    p_curate.add_argument("--file", help="read the statement from a file")
    p_curate.set_defaults(func=_cmd_curate)

    p_fetch = sub.add_parser("fetch", help="fetch a LeetCode problem and auto-curate it")
    p_fetch.add_argument(
        "title_slug", nargs="?", help="LeetCode problem slug (URL path), e.g. two-sum"
    )
    p_fetch.add_argument(
        "--all", action="store_true",
        help="land every roadmap problem (no curation — the content batch runner)",
    )
    p_fetch.add_argument(
        "--no-curate", action="store_true",
        help="land without running the curator",
    )
    p_fetch.set_defaults(func=_cmd_fetch)

    p_reference = sub.add_parser(
        "reference", help="generate the canonical reference a problem is measured against"
    )
    p_reference.add_argument("slug", nargs="?", help="problem slug")
    p_reference.add_argument(
        "--all", action="store_true", help="every curated problem that lacks a reference"
    )
    p_reference.add_argument(
        "--force", action="store_true", help="replace an existing reference"
    )
    p_reference.set_defaults(func=_cmd_reference)

    p_report = sub.add_parser("report", help="audit a problem's curation (AI); --fix re-curates")
    p_report.add_argument("slug", nargs="?", help="problem slug (default: active session)")
    p_report.add_argument(
        "--note",
        default=None,
        metavar="TEXT",
        help="what you observed, in your words — the auditor answers it",
    )
    p_report.add_argument(
        "--fix",
        action="store_true",
        help="re-curate through the pipeline when the audit verdict is 'fix'",
    )
    p_report.set_defaults(func=_cmd_report)

    p_rebuild = sub.add_parser(
        "rebuild-cards", help="re-derive every warm-up card from your attempt history"
    )
    p_rebuild.add_argument(
        "--spread", type=int, default=7,
        help="spread an overdue never-recalled backlog over N days (default 7)",
    )
    p_rebuild.set_defaults(func=_cmd_rebuild_cards)
    return parser


PARSER = _build_parser()
COMMANDS = set(PARSER._subparsers._group_actions[0].choices)  # noqa: SLF001
USER_COMMANDS = {"day", "warmup", "learn", "profile", "history", "progress", "roadmap", "list"}


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
                    conf_path=DOJO_CONF,
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


HELP_TEXT = """\
dojo — AI-guided interview prep

One command a day: `dojo` runs the whole routine — warm-ups, then a
problem picked in roadmap order (prerequisites gated), solved in your own editor with a
never-solve tutor, graded honestly (isolated judge + empirical profiler +
AI review), and scheduled for spaced recall.

Usage:
  dojo                  the daily routine
  dojo <problem-slug>   the routine on one specific problem
  dojo --version        the version (pyproject.toml is its source of truth)

Commands:
  learn [TOPIC]   study a topic with the teacher, then practice a problem
  roadmap         the progression tree (solved · next up · locked)
  list            the problem bank (✓ = curated, ready to solve)
  progress        per-pattern proficiency + retention schedule
  history         your attempts, newest first (`show <id>` for detail)
  fetch SLUG      fetch a LeetCode problem and auto-curate it
  user [NAME]     switch the active user
  setup           re-run the setup wizard

First run: `uv run dojo` from the repo — a one-time wizard handles the
API key (detected automatically if it's in your environment), your name,
and installing the `dojo` command on your PATH.
"""


def _print_help() -> int:
    print(HELP_TEXT)
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # `dojo help` = `dojo -h` = `dojo --help` (and any trailing words): the
    # minimal guide, no argparse noise (v0.9). Subcommand help
    # (`dojo learn -h`) stays argparse-native.
    if raw and raw[0] in ("-h", "--help", "help"):
        return _print_help()
    argv = _normalize_argv(raw, COMMANDS)
    args = PARSER.parse_args(argv)
    if args.command is None:
        return _print_help()
    if args.command not in ("setup", "update"):
        from dojo.updater import auto_update

        auto_update()
    console = Console()
    if args.command != "setup":
        # A row whose problem file is gone is pruned here, and the student is
        # told: a shrinking bank must never be silent (v0.13 follow-up).
        ensure_seeded(DB_PATH, note=console.print)
    if args.command in USER_COMMANDS:
        args._user = _resolve_for_dispatch(args, console)
        _migrate_cards(console, args._user)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    except EOFError:
        # Ctrl-D (or a piped script running out of lines) at a prompt. It used
        # to surface as a traceback out of `rich.Console.input`; the session's
        # state file is left in place, so the same command resumes it (v0.13).
        print(
            "[dim]Input ended — stopping here. Your session is saved: run the "
            "same command to resume it.[/dim]"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
