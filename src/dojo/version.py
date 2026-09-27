"""dojo's version: ``<major>.<phase>.<commit>`` — from pyproject.toml and git.

`pyproject.toml` is the source of truth for the **base** (``<major>.<phase>.0``),
and the third component is a fact about the checkout rather than a number
somebody remembers to edit: it is how many commits have landed since the phase
was completed, counted by ``git describe`` from the tag that marks it.

    1.15.5   →  major 1 (a manual decision)
                15 phases completed
                5 commits since phase 15 was completed

**The ritual when a phase completes** — one commit, and nothing else ever:

1. ``pyproject.toml`` → ``version = "<major>.<phase>.0"``. The phase number is
   the roadmap stage (v0.13 → ``0.13.0``); bump the major by hand whenever you
   want a new epoch.
2. ``git tag v<major>.<phase>.0`` **on that same commit**.

Every commit after it moves the third component on its own, so the number cannot
drift from the history it claims to describe. A checkout with no such tag (an
installed wheel, a shallow clone, a tarball) falls back to the exact string in
`pyproject.toml`: the base is always pyproject's, git only refines it.

`PHASE_VERSION` (``<major>.<phase>``) is what gates debug-log retention — a phase
is a stage, so completing one clears `data/logs/`, while the commits *inside* a
phase accumulate without throwing history away.

(Why this file exists at all: there used to be three answers to one question —
the tag said ``0.13.0``, ``MAJOR_VERSION`` said ``"0.10"``, and
``dojo.__version__`` said ``0.1.0`` — so the debug-log guard its own docstring
mandated had not fired for two stages. Audit F13.)
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path
from typing import Callable

#: `<repo>/pyproject.toml` — this file lives at `<repo>/src/dojo/version.py`.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
_REPO_ROOT = _PYPROJECT.parent

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _parse(version: str | None) -> tuple[int, int, int] | None:
    """``"1.15.5"`` → ``(1, 15, 5)``; ``"0.13"`` → ``(0, 13, 0)``.

    Anything that is not ``major[.phase[.commit]]`` is rejected rather than
    guessed at: a version nobody can parse is a version nobody can trust."""
    if not version:
        return None
    match = _VERSION_RE.match(version.strip())
    if match is None:
        return None
    major, phase, commit = match.groups()
    return int(major), int(phase), int(commit or 0)


def _pyproject_version() -> str | None:
    try:
        data = tomllib.loads(_PYPROJECT.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    version = (data.get("project") or {}).get("version")
    return version if isinstance(version, str) and version else None


def _installed_version() -> str | None:
    """The wheel's metadata, for an installed dojo with no checkout beside it."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("dojo")
    except PackageNotFoundError:
        return None


def _default_runner() -> Runner:
    def run(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, cwd=_REPO_ROOT, capture_output=True, text=True, timeout=5
        )

    return run


def commits_since_phase(major: int, phase: int, run: Runner | None = None) -> int | None:
    """How many commits have landed since the tag that completed this phase.

    ``None`` means git cannot say — no checkout, no tag, or a shallow clone that
    does not carry it — and the caller then keeps pyproject's own third
    component. ``run`` is injectable so the suite never shells out."""
    runner = run or _default_runner()
    base = f"v{major}.{phase}"
    try:
        result = runner(
            [
                "git",
                "describe",
                "--tags",
                "--long",
                # Both spellings, since the tag may be written either way.
                "--match",
                base,
                "--match",
                f"{base}.*",
            ]
        )
    except Exception:  # noqa: BLE001 - a missing git must not break a run
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    # `v0.13.0-7-gabc1234`: the tag, the distance, the abbreviated commit.
    described = (result.stdout or "").strip()
    parts = described.rsplit("-", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    if not parts[0].lstrip("v").startswith(f"{major}.{phase}"):
        return None  # a tag from another phase: not this phase's distance
    return int(parts[1])


def _resolve() -> str:
    parsed = _parse(_pyproject_version()) or _parse(_installed_version())
    if parsed is None:
        return "0.0.0"
    major, phase, commit = parsed
    distance = commits_since_phase(major, phase)
    return f"{major}.{phase}.{commit if distance is None else distance}"


#: The full version, e.g. ``0.13.7`` — major.phases-completed.commits-since.
VERSION = _resolve()

#: ``<major>.<phase>``: the marker the debug log compares against, so finishing a
#: phase clears `data/logs/` and the commits inside a phase do not.
PHASE_VERSION = ".".join(VERSION.split(".")[:2])
