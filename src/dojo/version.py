"""dojo's version: ``<major>.<phase>.<commit>`` — written in pyproject, proved by git.

**The version is a fact about the checkout, and `pyproject.toml` mirrors it.** git
is authoritative for the third component — it is how many commits have landed
since the tag that completed the phase — and `pyproject.toml` carries the same
number so anything that reads the file (a shell prompt, a packaging tool, a
human) sees the real version rather than a phase base.

    0.13.7   →  major 0 (a manual decision)
                13 phases completed
                7 commits since phase 13 was completed

**Every commit keeps `pyproject.toml` in step: run `make version`.** It writes the
version of the state you are in — with uncommitted work, the number that work will
be committed as (`commits_since_phase() + 1`); on a clean tree, the current one, so
a casual run cannot invent a commit that does not exist. `tests/test_version.py`
fails when the file and the history disagree — so a forgotten bump is caught by the
suite, not by a stale prompt later.

**Completing a phase** is that same bump plus two manual touches, in one commit:

1. ``pyproject.toml`` → ``version = "<major>.<phase>.0"`` (the phase number is the
   roadmap stage: v0.13 → ``0.13.0``; bump the major by hand for a new epoch).
2. ``git tag v<major>.<phase>.0`` **on that commit** — the mark the next phase's
   commits are counted from.

A checkout with no such tag (an installed wheel, a shallow clone, a tarball) falls
back to the exact string in `pyproject.toml` — which is why keeping the file
current matters: it is what a packaged dojo reports about itself.

**An epoch bump does not orphan the phase tag.** The major is a manual decision, and
it is taken *after* the tag that completed the last phase was written: phase 13's
marker is `v0.13.0` and stays that way forever, so a checkout at `1.13.11` is still
counting commits from `v0.13.0`. `commits_since_phase` therefore looks for the exact
`v<major>.<phase>` spelling first and falls back to *any* major with this phase —
without that, the epoch bump silently degrades the count to "whatever
`pyproject.toml` says", which is precisely the drift this module exists to prevent.

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


def _describe(
    runner: Runner, patterns: list[str], *, major: int | None, phase: int
) -> tuple[str, int] | None:
    """Ask git for the nearest tag matching `patterns`; return (tag, distance).

    The tag is accepted only when its *phase* matches — and its major too, when one
    was demanded — so a leftover tag from another phase can never be mistaken for
    this phase's marker, and the count never spans phases."""
    cmd = ["git", "describe", "--tags", "--long"]
    for pattern in patterns:
        cmd += ["--match", pattern]
    try:
        result = runner(cmd)
    except Exception:  # noqa: BLE001 - a missing git must not break a run
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    # `v0.13.0-7-gabc1234`: the tag, the distance, the abbreviated commit.
    parts = (result.stdout or "").strip().rsplit("-", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    tag = parts[0]
    parsed = _parse(tag.lstrip("v"))
    if parsed is None:
        return None
    tag_major, tag_phase, _tag_commit = parsed
    if tag_phase != phase or (major is not None and tag_major != major):
        return None
    return tag, int(parts[1])


def _find_phase_tag(
    major: int, phase: int, run: Runner | None = None
) -> tuple[str, int] | None:
    """The tag this checkout counts from for `phase`, and the distance to HEAD.

    Two passes, because of the epoch bump: the exact `v<major>.<phase>` spelling
    first, then any major carrying this phase. Phase 13's tag is `v0.13.0` and stays
    that way after a hand-bumped major, so `1.13.11` still means "eleven commits
    since `v0.13.0`". ``None`` means git cannot answer — no checkout, no such tag,
    a shallow clone that does not carry it — and the caller then keeps
    `pyproject.toml`'s own third component."""
    runner = run or _default_runner()
    base = f"v{major}.{phase}"
    passes = (
        ([base, f"{base}.*"], major),
        ([f"v*.{phase}", f"v*.{phase}.*"], None),
    )
    for patterns, demanded_major in passes:
        found = _describe(runner, patterns, major=demanded_major, phase=phase)
        if found is not None:
            return found
    return None


def phase_tag(major: int, phase: int, run: Runner | None = None) -> str | None:
    """The tag that completed this phase, whatever major it carries (or None)."""
    found = _find_phase_tag(major, phase, run=run)
    return found[0] if found is not None else None


def commits_since_phase(major: int, phase: int, run: Runner | None = None) -> int | None:
    """How many commits have landed since the tag that completed this phase.

    ``run`` is injectable so the suite never shells out."""
    found = _find_phase_tag(major, phase, run=run)
    return found[1] if found is not None else None


def _resolve(run: Runner | None = None) -> str:
    """The version this checkout *is*: git's distance when git can answer, else
    the string in `pyproject.toml` verbatim (a wheel, a tarball, a shallow clone)."""
    parsed = _parse(_pyproject_version()) or _parse(_installed_version())
    if parsed is None:
        return "0.0.0"
    major, phase, commit = parsed
    distance = commits_since_phase(major, phase, run=run)
    return f"{major}.{phase}.{commit if distance is None else distance}"


def pending_version(run: Runner | None = None) -> str:
    """The version the **next commit** will have — what `make version` writes.

    One more than the current distance, because the commit being prepared becomes
    part of the history the number describes. When git cannot answer — a phase
    whose tag does not exist yet, or no checkout — the file's own value stands,
    which is exactly right at a phase boundary: that commit *is* the tag, so
    nothing has been added to the count yet."""
    parsed = _parse(_pyproject_version()) or _parse(_installed_version())
    if parsed is None:
        return "0.0.0"
    major, phase, commit = parsed
    distance = commits_since_phase(major, phase, run=run)
    if distance is None:
        return f"{major}.{phase}.{commit}"
    return f"{major}.{phase}.{distance + 1}"


def write_pyproject(version: str, path: Path | None = None) -> Path:
    """Set ``[project].version`` in pyproject.toml, touching nothing else."""
    target = path or _PYPROJECT
    text = target.read_text()
    start = text.find("[project]")
    if start == -1:
        raise RuntimeError(f"{target} has no [project] table")
    head, sep, tail = text.partition("[project]")
    replaced, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        tail,
        count=1,
    )
    if not count:
        raise RuntimeError(f"{target} has no version line in [project]")
    target.write_text(head + sep + replaced)
    return target


def tree_has_changes(run: Runner | None = None) -> bool:
    """Whether the working tree carries changes beyond pyproject.toml's own
    version line — i.e. whether a commit is in flight.

    This is what makes `make version` honest in both states: with uncommitted
    work, the tree is one commit away from HEAD, so the version it will be
    committed as is `commits_since_phase() + 1`; on a clean tree the current
    version stands, and a casual run must not invent a commit that does not
    exist. A checkout without git counts as clean — nothing can be committed
    there anyway, and nothing is pending."""
    runner = run or _default_runner()
    try:
        result = runner(["git", "status", "--porcelain"])
    except Exception:  # noqa: BLE001 - no git: nothing to be pending
        return False
    if getattr(result, "returncode", 1) != 0:
        return False
    for line in (result.stdout or "").splitlines():
        path = line[3:].strip() if len(line) > 3 else ""
        if path and Path(path).name != _PYPROJECT.name:
            return True
    return False


def sync_pyproject(run: Runner | None = None) -> tuple[str, bool]:
    """Bring `pyproject.toml` in step with the state you are in; (version, changed).

    With uncommitted work that is the number the work will be committed as
    (`pending_version()`); on a clean tree it is the current version. So the file
    never describes a commit that does not exist, running it twice in a row is a
    no-op, and it is safe on a checkout whose git it cannot read. This is
    `make version`."""
    current = _resolve(run=run)
    target = pending_version(run=run) if tree_has_changes(run=run) else current
    if _parse(target) is None:
        return current, False
    if _pyproject_version() == target:
        return target, False
    write_pyproject(target)
    return target, True


#: The full version, e.g. ``0.13.7`` — major.phases-completed.commits-since.
VERSION = _resolve()

#: ``<major>.<phase>``: the marker the debug log compares against, so finishing a
#: phase clears `data/logs/` and the commits inside a phase do not.
PHASE_VERSION = ".".join(VERSION.split(".")[:2])

