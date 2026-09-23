"""One source of truth for the version: `pyproject.toml` (audit F13).

There used to be three answers to one question — the tag said `0.13.0`,
`version.MAJOR_VERSION` said `"0.10"`, and `dojo.__version__` said `0.1.0`.
`MAJOR_VERSION` gates debug-log retention, so the drift had a cost: the guard
its own docstring mandates had not fired for two stages.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import dojo
from dojo import version as version_mod
from dojo.debuglog import MAJOR_VERSION as DEBUGLOG_MAJOR

REPO_ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


def test_version_is_the_pyproject_version():
    assert version_mod.VERSION == _project_version()
    # `dojo.__version__` is the same value, not a second opinion.
    assert dojo.__version__ == _project_version()


def test_major_version_is_the_derived_major_minor():
    """The debug-log guard compares major.minor, so a patch release keeps the
    log and a new stage clears it."""
    assert version_mod.MAJOR_VERSION == ".".join(_project_version().split(".")[:2])
    assert DEBUGLOG_MAJOR == version_mod.MAJOR_VERSION


def test_a_missing_checkout_falls_back_to_installed_metadata(monkeypatch, tmp_path):
    """An installed dojo with no checkout beside it still knows its version."""
    monkeypatch.setattr(version_mod, "_PYPROJECT", tmp_path / "pyproject.toml")
    assert version_mod._pyproject_version() is None
    installed = version_mod._installed_version()
    assert installed is None or isinstance(installed, str)


def test_unreadable_pyproject_is_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(version_mod, "_PYPROJECT", tmp_path)
    assert version_mod._pyproject_version() is None


def test_nothing_hardcodes_a_version_literal():
    """The failure mode was a *hardcoded* second answer, not a missing import:
    a literal assignment is what drifts."""
    pattern = re.compile(r'''^(MAJOR_VERSION|VERSION|__version__)\s*=\s*["'][^"']*["']\s*$''')
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {line.strip()}"
        for path in (REPO_ROOT / "src").rglob("*.py")
        for line in path.read_text().splitlines()
        if pattern.match(line.strip())
    ]
    assert offenders == [], f"version literals outside pyproject.toml: {offenders}"
