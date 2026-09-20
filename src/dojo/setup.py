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
from dojo.config import PROVIDERS, key_env_names, save_conf
from dojo.db import connect, now


#: The variable a pasted key is stored under when the provider is unknown — the
#: default provider, so an unqualified key keeps working exactly as before.
DEFAULT_KEY_ENV = "DEEPSEEK_API_KEY"


def write_key(dotenv_path: Path, key: str, env_name: str = DEFAULT_KEY_ENV) -> None:
    """Append a provider key to a dotenv file, preserving other lines."""
    lines = dotenv_path.read_text().splitlines() if dotenv_path.exists() else []
    lines = [line for line in lines if not line.startswith(f"{env_name}=")]
    lines.append(f"{env_name}={key}")
    dotenv_path.write_text("\n".join(lines) + "\n")


def write_setting(dotenv_path: Path, name: str, value: str) -> None:
    """Set a non-secret dotenv setting (e.g. `DOJO_PROVIDER`)."""
    lines = dotenv_path.read_text().splitlines() if dotenv_path.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    dotenv_path.write_text("\n".join(lines) + "\n")


def read_dotenv_key(dotenv_path: Path, env_name: str = DEFAULT_KEY_ENV) -> str | None:
    """The key already saved in a dotenv file, if any (same parsing as
    config._read_dotenv, against an injected path)."""
    if not dotenv_path.exists():
        return None
    for line in dotenv_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == env_name:
            return v.strip().strip("'\"")
    return None


def detect_key(
    dotenv_path: Path, provider_override: str | None = None
) -> tuple[str, str] | None:
    """(provider, key) from the environment or *this* dotenv file.

    The wizard takes its dotenv as a parameter (tests run against tmp paths), so
    detection has to look there too — `config.detect_provider_key` reads the
    repo-root `.env`, which is the right thing for a live run and the wrong thing
    for the wizard.
    """
    order = (
        [provider_override]
        if provider_override in PROVIDERS
        else list(PROVIDERS)
    )
    for name in order:
        provider = PROVIDERS[name]
        for env_name in key_env_names(provider):
            value = os.environ.get(env_name) or read_dotenv_key(dotenv_path, env_name)
            if value:
                return name, value
    return None


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
    detect_env_key: bool = True,
    provider_override: str | None = None,
) -> dict:
    """The full first-run flow. Returns a summary dict; never raises on
    user-facing steps (a bad key prompt just skips the key).

    Key resolution (v0.9, provider-aware v0.13): when detection is on, a key for
    any provider in the table (environment or the dotenv file) is used without
    prompting, and the provider that owns it becomes the configured one
    (``DOJO_PROVIDER`` is written to the dotenv) — an env-sourced key is also
    persisted so it survives other shells. Only when nothing is detected does the
    injected ``key_getter`` run, storing under the pinned provider's variable
    when ``provider_override`` names one."""
    console.print("[bold]Welcome to dojo — one-time setup.[/bold]")

    # Key resolution (v0.13): every provider in the table is checked (env first,
    # then the gitignored dotenv), and the provider that owns the key becomes the
    # configured one. `dojo setup --provider X` pins the choice.
    detected = detect_key(dotenv_path, provider_override) if detect_env_key else None
    key_written = False
    if detected:
        provider_name, key = detected
        provider = PROVIDERS[provider_name]
        if read_dotenv_key(dotenv_path, provider.key_env) != key:
            write_key(dotenv_path, key, provider.key_env)
            key_written = True
        write_setting(dotenv_path, "DOJO_PROVIDER", provider_name)
        console.print(
            f"[green]{provider.key_env} detected — using {provider_name} "
            f"({provider.model}), no prompt needed.[/green]"
            + (" Saved to .env (gitignored) so every shell sees it." if key_written else "")
        )
    elif key_getter is not None:
        key = key_getter().strip()
        if key:
            env_name = (
                PROVIDERS[provider_override].key_env
                if provider_override in PROVIDERS
                else DEFAULT_KEY_ENV
            )
            write_key(dotenv_path, key, env_name)
            if provider_override in PROVIDERS:
                write_setting(dotenv_path, "DOJO_PROVIDER", provider_override)
            key_written = True
            console.print(
                f"[green]{env_name} saved to {dotenv_path.name}[/green] "
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
        # Scoped to the user this wizard just registered: backfilling every user
        # inflated the count and created due-immediately cards for someone else.
        backfilled = scheduler.backfill_cards(conn, user_id) if user_id else 0
    save_conf({"user": name}, conf_path)

    installed = False
    if path_install is not None:
        installed = bool(path_install())
    next_step = "`dojo`" if installed else "`uv run dojo` from this repo (or `dojo setup` to install `dojo` on your PATH)"
    console.print(
        f"[green]You're set.[/green] Imported {seeded} problems, registered "
        f"'{name}'"
        + (f", backfilled {backfilled} card(s)" if backfilled else "")
        + (", installed `dojo` on PATH" if installed else "")
        + f". Next: {next_step}."
    )
    return {
        "user": name,
        "seeded": seeded,
        "backfilled": backfilled,
        "key_written": key_written,
        "key_detected": bool(detected),
        "path_installed": installed,
    }
