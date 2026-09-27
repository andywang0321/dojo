"""The version scheme: ``<major>.<phase>.<commit>``, from pyproject + git.

`pyproject.toml` is the source of truth for the base — ``<major>.<phase>.0`` —
and the third component is how many commits have landed since the tag that
completed the phase, so it is a fact about the checkout rather than a number
somebody remembers to edit. These tests pin the derivation *and* the fact: the
last one re-counts the commits in git and compares.

(There used to be three answers to one question — the tag said `0.13.0`,
`MAJOR_VERSION` said `"0.10"`, and `dojo.__version__` said `0.1.0` — and the
drift silently disabled the debug-log retention gate for two stages. F13.)
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

import dojo
from dojo import version as version_mod
from dojo.debuglog import PHASE_VERSION as DEBUGLOG_PHASE

REPO_ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


# ------------------------------------------------------------ what it reads


def test_the_base_comes_from_pyproject():
    """`pyproject.toml` decides major and phase. The third component is git's —
    so the assertion is on the base, not on whole-string equality."""
    assert version_mod.VERSION.split(".")[:2] == _project_version().split(".")[:2]
    assert version_mod.VERSION.split(".")[2].isdigit()
    # `dojo.__version__` is the same value, not a second opinion.
    assert dojo.__version__ == version_mod.VERSION


def test_phase_version_is_major_dot_phase_and_gates_the_debug_log():
    """A phase is a stage: completing one clears `data/logs/`, the commits inside
    it do not."""
    assert version_mod.PHASE_VERSION == ".".join(version_mod.VERSION.split(".")[:2])
    assert DEBUGLOG_PHASE == version_mod.PHASE_VERSION


def test_parse_accepts_two_or_three_components_and_rejects_nonsense():
    assert version_mod._parse("1.15.5") == (1, 15, 5)
    assert version_mod._parse("0.13") == (0, 13, 0)
    assert version_mod._parse(" 2.04.10 ") == (2, 4, 10)
    for bad in ("", None, "banana", "0.13.0rc1", "v0.13.0", "1.15.5.2", "-1.2.3"):
        assert version_mod._parse(bad) is None


# ------------------------------------------------------- the commit distance


def test_the_third_component_is_the_distance_from_the_phase_tag(monkeypatch):
    """The reported example: `1.15.5` = major 1, phase 15 complete, five commits
    since. Nothing in the tree stores that `5` — git answers it."""
    monkeypatch.setattr(version_mod, "commits_since_phase", lambda *a, **k: 5)
    monkeypatch.setattr(version_mod, "_pyproject_version", lambda: "1.15.0")
    assert version_mod._resolve() == "1.15.5"


def test_the_query_names_this_phases_tag():
    """`git describe` must be asked for *this* phase's tag, not the nearest tag of
    any phase — otherwise the count would span phases."""
    seen: list[list[str]] = []

    def runner(cmd):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout="v0.13.0-7-gabc1234\n")

    assert version_mod.commits_since_phase(0, 13, run=runner) == 7
    cmd = seen[0]
    assert cmd[:2] == ["git", "describe"]
    assert "--long" in cmd                    # the distance, not just the tag name
    assert "v0.13" in cmd and "v0.13.*" in cmd


def test_a_describe_for_another_phase_is_refused():
    """A tag left over from a previous phase must not be mistaken for this one's."""
    stale = SimpleNamespace(returncode=0, stdout="v0.12.0-31-gdeadbee\n")
    assert version_mod.commits_since_phase(0, 13, run=lambda cmd: stale) is None


def test_a_wheel_or_a_shallow_clone_falls_back_to_pyproject(monkeypatch):
    """No tag, no git, a git that errors: the string in `pyproject.toml` stands
    as written. The base is always pyproject's; git only refines it."""
    monkeypatch.setattr(version_mod, "commits_since_phase", lambda *a, **k: None)
    monkeypatch.setattr(version_mod, "_pyproject_version", lambda: "1.15.0")
    assert version_mod._resolve() == "1.15.0"
    # ... and a hand-written third component is kept verbatim in that case.
    monkeypatch.setattr(version_mod, "_pyproject_version", lambda: "1.15.3")
    assert version_mod._resolve() == "1.15.3"


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(returncode=128, stdout=""),          # no such tag
        SimpleNamespace(returncode=0, stdout="garbage"),     # not describe output
        SimpleNamespace(returncode=0, stdout="v0.13.0-x-g1"),  # not a number
    ],
)
def test_unusable_git_output_is_not_an_error(result):
    assert version_mod.commits_since_phase(0, 13, run=lambda cmd: result) is None


def test_a_missing_git_binary_is_not_an_error():
    def runner(cmd):
        raise FileNotFoundError("git")

    assert version_mod.commits_since_phase(0, 13, run=runner) is None


def test_pyproject_is_kept_in_step_with_the_history():
    """`pyproject.toml` is what a shell prompt and a packaging tool read, so it
    carries the *current* version rather than a phase base — `make version` writes
    it as part of every commit (AGENTS rule 9).

    Two values are legal, because the check also runs before the commit exists:
    the version of HEAD (already committed, `VERSION`), or the version that commit
    is about to have (`pending_version()`). Anything else means someone landed a
    commit without the bump — which is exactly what this test is for."""
    declared = _project_version()
    current = version_mod.VERSION
    pending = version_mod.pending_version()
    assert declared in (current, pending), (
        f"pyproject.toml says {declared}; the history says {current} and the next "
        f"commit will be {pending} — run `make version`"
    )


def test_uncommitted_work_gets_the_number_it_will_be_committed_as(monkeypatch, tmp_path):
    """`make version` = `sync_pyproject()`: with work in the tree, write the number
    that work will have, touch nothing else, and be a no-op the second time."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "dojo"\nversion = "1.15.0"\n\n[tool.other]\nversion = "keep-me"\n'
    )
    monkeypatch.setattr(version_mod, "_PYPROJECT", pyproject)
    monkeypatch.setattr(version_mod, "commits_since_phase", lambda *a, **k: 4)
    monkeypatch.setattr(version_mod, "tree_has_changes", lambda *a, **k: True)

    assert version_mod.sync_pyproject() == ("1.15.5", True)
    text = pyproject.read_text()
    assert 'version = "1.15.5"' in text
    assert 'version = "keep-me"' in text            # only [project] is touched
    assert 'name = "dojo"' in text                  # ... and only that one line
    assert version_mod.sync_pyproject() == ("1.15.5", False)   # idempotent


def test_a_clean_tree_keeps_the_current_version(monkeypatch, tmp_path):
    """Running it when there is nothing to commit must not invent a commit: the
    file is what a shell prompt reads, so it has to describe the state you are in
    (this is the bug the first version had — it wrote `derived + 1` always)."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.15.0"\n')
    monkeypatch.setattr(version_mod, "_PYPROJECT", pyproject)
    monkeypatch.setattr(version_mod, "commits_since_phase", lambda *a, **k: 4)
    monkeypatch.setattr(version_mod, "tree_has_changes", lambda *a, **k: False)

    assert version_mod.sync_pyproject() == ("1.15.4", True)
    assert 'version = "1.15.4"' in pyproject.read_text()
    assert version_mod.sync_pyproject() == ("1.15.4", False)


def test_a_dirty_tree_is_recognised_by_git(monkeypatch):
    """The state probe itself: lines mentioning pyproject.toml alone are not work."""
    clean = SimpleNamespace(returncode=0, stdout="")
    only_pyproject = SimpleNamespace(returncode=0, stdout=' M pyproject.toml\n')
    real_work = SimpleNamespace(
        returncode=0, stdout=' M pyproject.toml\n?? src/dojo/new.py\n'
    )
    assert version_mod.tree_has_changes(run=lambda cmd: clean) is False
    assert version_mod.tree_has_changes(run=lambda cmd: only_pyproject) is False
    assert version_mod.tree_has_changes(run=lambda cmd: real_work) is True
    assert version_mod.tree_has_changes(run=lambda cmd: SimpleNamespace(returncode=128, stdout="")) is False

    def no_git(cmd):
        raise FileNotFoundError("git")

    assert version_mod.tree_has_changes(run=no_git) is False


def test_at_a_phase_boundary_the_new_base_stands(monkeypatch, tmp_path):
    """The commit that completes a phase *is* the tag, so nothing is added to the
    count yet: `make version` writes `1.15.0` and the tag is created on it."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.15.0"\n')
    monkeypatch.setattr(version_mod, "_PYPROJECT", pyproject)
    monkeypatch.setattr(version_mod, "commits_since_phase", lambda *a, **k: None)
    assert version_mod.sync_pyproject() == ("1.15.0", False)


def test_the_writer_refuses_a_pyproject_it_cannot_edit(monkeypatch, tmp_path):
    bad = tmp_path / "pyproject.toml"
    bad.write_text('[build-system]\nrequires = ["hatchling"]\n')
    monkeypatch.setattr(version_mod, "_PYPROJECT", bad)
    with pytest.raises(RuntimeError, match=r"\[project\]"):
        version_mod.write_pyproject("1.0.0")


def test_the_commit_count_matches_the_history_it_describes():
    """The number claims to be a fact, so re-count it: the checkout's version must
    equal `git rev-list --count v<major>.<phase>.0..HEAD`. Skipped where there is
    no checkout or no phase tag (a wheel, a shallow clone, a fresh fork)."""
    major, phase, commit = version_mod.VERSION.split(".")
    if version_mod.commits_since_phase(int(major), int(phase)) is None:
        pytest.skip("no git checkout carrying this phase's tag")
    counted = _git("rev-list", "--count", f"v{major}.{phase}.0..HEAD")
    if counted.returncode != 0:
        pytest.skip(f"tag v{major}.{phase}.0 is not in this checkout")
    assert int(commit) == int(counted.stdout.strip())


# ------------------------------------------------------------- the fallbacks


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
    a literal assignment is what drifts. The derived `0.13.N` must never be
    written down anywhere — it would be stale one commit later."""
    pattern = re.compile(
        r'''^(MAJOR_VERSION|PHASE_VERSION|VERSION|__version__)\s*=\s*["'][^"']*["']\s*$'''
    )
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {line.strip()}"
        for path in (REPO_ROOT / "src").rglob("*.py")
        for line in path.read_text().splitlines()
        if pattern.match(line.strip())
    ]
    assert offenders == [], f"version literals outside pyproject.toml: {offenders}"
