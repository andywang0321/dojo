"""The dojo CLI.

  dojo init [--user NAME ...]   create the DB, seed the problem bank
  dojo list [--pattern P]       catalog, with solved status
  dojo day [SLUG] [--user N]    warm-ups (if due) + solve session
  dojo warmup [--user NAME]     run due warm-up retrievals only
  dojo check [SLUG]             visible tests on the current workbench
  dojo profile [--user NAME]    your attempt history
  dojo progress [--user NAME]   per-pattern proficiency + card schedule
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table

from dojo import scheduler
from dojo.bank import seed_problems
from dojo.config import DB_PATH, PROBLEMS_DIR
from dojo.db import connect, get_or_create_user, init_db, now


def _cmd_init(args) -> int:
    init_db(DB_PATH)
    n = seed_problems(connect(DB_PATH), PROBLEMS_DIR)
    console = Console()
    console.print(f"[green]Seeded {n} problems into {DB_PATH}[/green]")
    with connect(DB_PATH) as conn:
        for name in args.user or []:
            conn.execute(
                "INSERT OR IGNORE INTO users (name, created_at) VALUES (?, datetime('now'))",
                (name,),
            )
        conn.commit()
        n_cards = scheduler.backfill_cards(conn)
        users = [r["name"] for r in conn.execute("SELECT name FROM users")]
    console.print(f"Users: {', '.join(users) or '(none yet — `dojo day` creates them on the fly)'}")
    if n_cards:
        console.print(f"[dim]Backfilled {n_cards} pattern card(s) from solved attempts (due now).[/dim]")
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
        if args.user:
            for r in conn.execute(
                """
                SELECT problem_id, status FROM attempts
                WHERE user_id = (SELECT id FROM users WHERE name = ?)
                """,
                (args.user,),
            ):
                solved[r["problem_id"]] = r["status"]
    table = Table(title="Problem bank")
    table.add_column("Problem")
    table.add_column("Difficulty")
    table.add_column("Pattern")
    table.add_column("Curated")
    table.add_column("Status" if args.user else "Solved")
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


def _cmd_day(args) -> int:
    from dojo.session import run_day, run_warmups
    from dojo.tutor import get_backend

    console = Console()
    user = args.user or "default"
    with connect(DB_PATH) as conn:
        try:
            backend = get_backend()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        if not args.skip_warmup:
            run_warmups(conn, console, backend, user, limit=2)
        slug = args.slug
        if slug is None:
            user_id = get_or_create_user(conn, user)
            problem = scheduler.pick_new_problem(conn, user_id)
            if problem is None:
                console.print(
                    "[green]Every curated problem is solved — nothing new to pick. "
                    "Run `dojo warmup` to keep patterns alive.[/green]"
                )
                return 0
            slug = problem["slug"]
            console.print(
                f"[bold]Scheduler pick:[/bold] {problem['title']} "
                f"({problem['pattern']}, {problem['difficulty']}) — weakest pattern first."
            )
        outcome = run_day(conn, console, backend, slug, user, open_editor=args.open)
    return 0 if outcome in ("solved", "quit", "warmup_done") else 1


def _cmd_warmup(args) -> int:
    from dojo.session import run_warmups
    from dojo.tutor import get_backend

    console = Console()
    with connect(DB_PATH) as conn:
        try:
            backend = get_backend()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        run_warmups(conn, console, backend, args.user or "default", limit=3)
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
            (args.user or "default",),
        ).fetchall()
    table = Table(title=f"Attempts — {args.user or 'default'}")
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


def _cmd_progress(args) -> int:
    console = Console()
    user = args.user or "default"
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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dojo", description="AI-guided interview prep: never-solve tutor + empirical grader."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create DB, seed problem bank")
    p_init.add_argument("--user", action="append", help="create a user (repeatable)")
    p_init.set_defaults(func=_cmd_init)

    p_list = sub.add_parser("list", help="list the problem bank")
    p_list.add_argument("--pattern", help="filter by pattern directory")
    p_list.add_argument("--user", help="show per-user solved status")
    p_list.set_defaults(func=_cmd_list)

    p_day = sub.add_parser("day", help="warm-ups (if due) + a solve session")
    p_day.add_argument("slug", nargs="?", help="problem slug (scheduler picks if omitted)")
    p_day.add_argument("--user", help="who is solving (default: 'default')")
    p_day.add_argument("--open", action="store_true", help="open $EDITOR right away (use the in-session `open` command instead)")
    p_day.add_argument("--skip-warmup", action="store_true", help="skip due warm-up retrievals")
    p_day.set_defaults(func=_cmd_day)

    p_warmup = sub.add_parser("warmup", help="run due warm-up retrievals only")
    p_warmup.add_argument("--user", help="who is practicing (default: 'default')")
    p_warmup.set_defaults(func=_cmd_warmup)

    p_check = sub.add_parser("check", help="run visible tests on the active workbench")
    p_check.add_argument("slug", nargs="?", help="problem slug (default: active session)")
    p_check.set_defaults(func=_cmd_check)

    p_profile = sub.add_parser("profile", help="show attempt history")
    p_profile.add_argument("--user", help="whose profile (default: 'default')")
    p_profile.set_defaults(func=_cmd_profile)

    p_progress = sub.add_parser("progress", help="per-pattern proficiency + card schedule")
    p_progress.add_argument("--user", help="whose progress (default: 'default')")
    p_progress.set_defaults(func=_cmd_progress)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
