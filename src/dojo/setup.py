"""The setup wizard (v0.5): first-run onboarding.

Pure, injectable logic: everything this module touches is a parameter
(dotenv path, conf path, db path, key prompt, PATH installer), so tests run
against tmp paths and never touch real state. The CLI shell in `cli.py`
wires the real values in.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from dojo import scheduler
from dojo.bank import ensure_seeded
from dojo.config import save_conf
from dojo.db import connect, now


def write_key(dotenv_path: Path, key: str) -> None:
    """Append DEEPSEEK_API_KEY to a dotenv file, preserving existing lines."""
    lines = dotenv_path.read_text().splitlines() if dotenv_path.exists() else []
    lines = [line for line in lines if not line.startswith("DEEPSEEK_API_KEY=")]
    lines.append(f"DEEPSEEK_API_KEY={key}")
    dotenv_path.write_text("\n".join(lines) + "\n")


def default_user_name(user_env: str | None, git_user: str | None) -> str:
    """A sensible default for the wizard's name prompt: $USER, else the
    first word of the git identity, lowercased."""
    if user_env:
        return user_env
    if git_user:
        return git_user.split()[0].lower()
    return ""


def wrapper_script(repo_root: str) -> str:
    """The ~/.local/bin/dojo wrapper: always-live code via uv run --project,
    so `git pull` updates flow through without reinstalling."""
    return f"#!/bin/sh\nexec uv run --project '{repo_root}' dojo \"$@\"\n"


def install_wrapper(bin_dir: Path, repo_root: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "dojo"
    path.write_text(wrapper_script(repo_root))
    path.chmod(0o755)
    return path


def rc_line(bin_dir: str) -> str:
    return f'export PATH="{bin_dir}:$PATH"'


def append_rc(rc_path: Path, line: str) -> None:
    """Append a line to a shell rc file, without duplicating it."""
    content = rc_path.read_text() if rc_path.exists() else ""
    if line in content:
        return
    rc_path.write_text(content.rstrip("\n") + "\n" + line + "\n")


def run_wizard(
    console,
    *,
    dotenv_path: Path,
    conf_path: Path,
    db_path: Path,
    problems_dir: Path,
    default_name: str = "",
    user_override: str | None = None,
    key_getter: Callable[[], str] | None = None,
    path_install: Callable[[], bool] | None = None,
) -> dict:
    """The full first-run flow. Returns a summary dict; never raises on
    user-facing steps (a bad key prompt just skips the key)."""
    console.print("[bold]Welcome to dojo — one-time setup.[/bold]")

    key_written = False
    if key_getter is not None:
        key = key_getter().strip()
        if key:
            write_key(dotenv_path, key)
            key_written = True
            console.print(
                f"[green]API key saved to {dotenv_path.name}[/green] "
                "(gitignored)."
            )
        else:
            console.print(
                "[yellow]No key — fine. Run with DOJO_AI_BACKEND=mock, or "
                "re-run `dojo setup` later.[/yellow]"
            )

    with connect(db_path) as conn:
        existing = [r["name"] for r in conn.execute("SELECT name FROM users")]
    if user_override:
        name = user_override
    else:
        fallback = existing[0] if existing else default_name
        raw = console.input(f"Your name (default '{fallback or 'user'}'): ").strip()
        name = raw or fallback or "user"
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (name, created_at) VALUES (?, ?)",
            (name, now()),
        )
        conn.commit()

    seeded = ensure_seeded(db_path, problems_dir)
    with connect(db_path) as conn:
        user_id = conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()["id"]
        backfilled = scheduler.backfill_cards(conn) if user_id else 0
    save_conf({"user": name}, conf_path)

    installed = False
    if path_install is not None:
        installed = bool(path_install())
    console.print(
        f"[green]You're set.[/green] Imported {seeded} problems, registered "
        f"'{name}'"
        + (f", backfilled {backfilled} card(s)" if backfilled else "")
        + (", installed `dojo` on PATH" if installed else "")
        + ". Next: `dojo`."
    )
    return {
        "user": name,
        "seeded": seeded,
        "backfilled": backfilled,
        "key_written": key_written,
        "path_installed": installed,
    }
