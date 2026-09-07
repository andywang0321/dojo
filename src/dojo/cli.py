"""The dojo CLI.

  dojo init [--user NAME ...]   create the DB, seed the problem bank
  dojo list [--pattern P]       catalog, with solved status
  dojo day [SLUG] [--user N]    start / resume a solve session
  dojo check [SLUG]             visible tests on the current workbench
  dojo profile [--user NAME]    your attempt history
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table

from dojo.bank import seed_problems
from dojo.config import DB_PATH, DSA_DIR
from dojo.db import connect, init_db


def _cmd_init(args) -> int:
    init_db(DB_PATH)
    n = seed_problems(connect(DB_PATH), DSA_DIR)
    console = Console()
    console.print(f"[green]Seeded {n} problems into {DB_PATH}[/green]")
    with connect(DB_PATH) as conn:
        for name in args.user or []:
            conn.execute(
                "INSERT OR IGNORE INTO users (name, created_at) VALUES (?, datetime('now'))",
                (name,),
            )
        conn.commit()
        users = [r["name"] for r in conn.execute("SELECT name FROM users")]
    console.print(f"Users: {', '.join(users) or '(none yet — `dojo day` creates them on the fly)'}")
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
    table.add_column("slug")
    table.add_column("title")
    table.add_column("difficulty")
    table.add_column("pattern")
    table.add_column("curated")
    table.add_column("status" if args.user else "solved")
    for r in rows:
        table.add_row(
            r["slug"],
            r["title"],
            r["difficulty"],
            r["pattern"],
            "✓" if r["function_name"] and r["visible_tests"] else "",
            solved.get(r["id"], "—"),
        )
    console.print(table)
    console.print(
        f"{len(rows)} problems. Curated = has function name + visible tests, ready for `dojo day`."
    )
    return 0


def _cmd_day(args) -> int:
    from dojo.session import run_day
    from dojo.tutor import get_backend

    console = Console()
    with connect(DB_PATH) as conn:
        slug = args.slug
        if slug is None:
            rows = conn.execute(
                """
                SELECT p.slug FROM problems p
                WHERE p.function_name IS NOT NULL AND p.visible_tests IS NOT NULL
                ORDER BY p.pattern, p.title
                """
            ).fetchall()
            if not rows:
                console.print("[red]No curated problems. Run `dojo init`.[/red]")
                return 1
            console.print("Curated problems:")
            for i, r in enumerate(rows, 1):
                console.print(f"  {i:>2}. {r['slug']}")
            choice = console.input("Pick a number (or slug): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(rows):
                slug = rows[int(choice) - 1]["slug"]
            else:
                slug = choice
        try:
            backend = get_backend()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        outcome = run_day(conn, console, backend, slug, args.user or "default", open_editor=args.open)
    return 0 if outcome in ("solved", "quit") else 1


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
        "problem", "difficulty", "status", "hints", "claimed time", "measured time",
        "r²", "claimed space", "measured space", "submitted",
    ):
        table.add_column(col)
    for r in rows:
        table.add_row(
            f"{r['title']} ({r['slug']})",
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

    p_day = sub.add_parser("day", help="start or resume a solve session")
    p_day.add_argument("slug", nargs="?", help="problem slug (pick interactively if omitted)")
    p_day.add_argument("--user", help="who is solving (default: 'default')")
    p_day.add_argument("--open", action="store_true", help="open $EDITOR right away (use the in-session `open` command instead)")
    p_day.set_defaults(func=_cmd_day)

    p_check = sub.add_parser("check", help="run visible tests on the active workbench")
    p_check.add_argument("slug", nargs="?", help="problem slug (default: active session)")
    p_check.set_defaults(func=_cmd_check)

    p_profile = sub.add_parser("profile", help="show attempt history")
    p_profile.add_argument("--user", help="whose profile (default: 'default')")
    p_profile.set_defaults(func=_cmd_profile)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
