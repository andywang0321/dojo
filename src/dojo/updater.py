"""dojo update + auto-update (v0.10.1): keep the checkout fresh.

`update_dojo` fast-forwards the repo (never a merge conflict — the repo
belongs to dojo, not to the user) and refreshes the venv only when the
pull changed files. The command runner is injectable so tests stay
offline, mirroring the fetcher's HTTP transport. Auto-update runs on
every CLI entry (except `setup`/`update`), is silenced by
``DOJO_NO_AUTO_UPDATE``, and can never break the run it precedes.
"""

from __future__ import annotations

import os
import subprocess
from typing import Callable

from dojo.config import REPO_ROOT

Runner = Callable[[list[str], int], subprocess.CompletedProcess]


def _default_runner() -> Runner:
    def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout
        )

    return run


def update_dojo(console=None, run: Runner | None = None, force: bool = False) -> str:
    """Fast-forward the repo to its upstream and refresh dependencies.
    Returns a human-readable outcome; never raises — an update problem
    must never break the run it precedes."""
    run = run or _default_runner()
    try:
        status = run(["git", "status", "--porcelain"])
        if status.returncode != 0:
            return "git unavailable — skipped update"
        if status.stdout.strip() and not force:
            return (
                "working tree has local changes — `dojo update --force` "
                "discards them"
            )
        fetch = run(["git", "fetch", "origin"], timeout=20)
        if fetch.returncode != 0:
            return "could not fetch (offline?) — skipped update"
        head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        upstream = run(["git", "rev-parse", "@{upstream}"]).stdout.strip()
        if head == upstream:
            return "already up to date"
        if force:
            pulled = run(["git", "reset", "--hard", upstream])
        else:
            pulled = run(["git", "merge", "--ff-only", upstream])
        if pulled.returncode != 0:
            return "update failed — `git pull` manually in the repo"
        head_after = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        if head_after == head:
            # Local contains upstream (or nothing new arrived): a no-op
            # merge must not be misreported as an update.
            return "already up to date"
    except (subprocess.SubprocessError, OSError):
        return "could not fetch (offline?) — skipped update"
    note = f"updated to {head_after[:8]}"
    try:
        sync = run(["uv", "sync", "--project", str(REPO_ROOT)], timeout=180)
        if sync.returncode != 0:
            note += " (dependency refresh failed — run `uv sync` in the repo)"
    except (subprocess.SubprocessError, OSError):
        note += " (dependency refresh failed — run `uv sync` in the repo)"
    return note


def auto_update() -> None:
    """Run at CLI start (v0.10.1): pull silently, note only what changed.
    Opt out with DOJO_NO_AUTO_UPDATE=1 (the agent/dev escape hatch)."""
    if os.environ.get("DOJO_NO_AUTO_UPDATE"):
        return
    from rich.console import Console

    console = Console()
    try:
        note = update_dojo(console)
    except Exception:  # noqa: BLE001 - auto-update must never break the run
        return
    if note and not note.startswith("already up to date") and "skipped" not in note:
        console.print(f"[dim]{note}[/dim]")
