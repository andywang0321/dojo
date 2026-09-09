"""The curation pipeline: proposal validation and apply-with-rollback.

`dojo curate` sends a raw problem statement to the curator agent (a separate
agent from the tutor — its outputs are judge infrastructure and must never
enter tutor context), then applies the artifacts and runs the verification
gate. On failure it rolls every touched file and registration back.

The apply step is deliberately mechanical: write the seed file, merge the
overrides entry, append the registry block, re-seed the DB, then run the
curation contract tests (tests/test_registry.py) as the acceptance gate.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from dojo import bank
from dojo.config import DB_PATH, PROBLEMS_DIR, PROBLEM_OVERRIDES, REPO_ROOT
from dojo.db import connect
from dojo.patterns import PATTERNS

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DIFFICULTIES = ("Easy", "Medium", "Hard")

REQUIRED_FIELDS = (
    "slug",
    "title",
    "difficulty",
    "pattern",
    "statement",
    "function_name",
    "signature",
    "visible_tests",
    "oracle_code",
    "judge_case_code",
)

_REGISTRY_DICTS = ("ORACLES", "JUDGE_CASES", "PROFILER_INPUTS", "CHECKERS")


class CuratorError(RuntimeError):
    """A proposal failed validation, application, or the verification gate."""


def validate(proposal: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in proposal]
    if missing:
        raise CuratorError(f"missing fields: {', '.join(missing)}")
    if not SLUG_RE.match(proposal["slug"]):
        raise CuratorError(f"bad slug {proposal['slug']!r} (want [a-z][a-z0-9_]*)")
    if proposal["difficulty"] not in DIFFICULTIES:
        raise CuratorError(f"bad difficulty {proposal['difficulty']!r}")
    if proposal["pattern"] not in PATTERNS:
        raise CuratorError(
            f"bad pattern {proposal['pattern']!r} (one of {', '.join(PATTERNS)})"
        )
    statement = proposal["statement"]
    if not bank._HEADER_RE.match(statement.splitlines()[0].strip()):
        raise CuratorError(
            "statement must start with a 'Title [Difficulty]' header line"
        )
    signature = proposal["signature"]
    if isinstance(signature, str):
        if not signature.startswith("("):
            raise CuratorError("function signature must start with '('")
    elif isinstance(signature, dict):
        if not ({"functions", "methods"} & set(signature)):
            raise CuratorError("dict signature needs 'functions' or 'methods'")
    else:
        raise CuratorError("signature must be a string or dict")
    tests = proposal["visible_tests"]
    if not isinstance(tests, list) or not 3 <= len(tests) <= 10:
        raise CuratorError("visible_tests must be a list of 3-10 cases")
    for case in tests:
        if not isinstance(case, dict) or ("args" not in case and "ops" not in case):
            raise CuratorError("each visible test needs 'args' or 'ops'")
        if "expected" not in case:
            raise CuratorError("each visible test needs 'expected'")
    for field in ("oracle_code", "judge_case_code", "checker_code", "profiler_code"):
        if field in proposal and proposal[field]:
            try:
                compile(proposal[field], f"<curator {field}>", "exec")
            except SyntaxError as exc:
                raise CuratorError(f"{field} does not compile: {exc}") from exc


def propose(backend, statement: str, hints: dict | None = None) -> dict:
    """Run the curator agent and validate its artifact set. ``hints``
    carries starter-code intel (function_name / signature / pattern) from
    the fetcher — the curator prefers it unless clearly wrong."""
    from dojo.curator.prompts import CURATOR_SYSTEM, build_curator_prompt

    raw = backend.chat_json(CURATOR_SYSTEM, build_curator_prompt(statement, hints))
    if "error" in raw:
        raise CuratorError(f"curator returned non-JSON: {raw['error']}")
    validate(raw)
    return raw


def _default_registry_namespace() -> tuple[dict, Path]:
    import dojo.judge.registry as registry

    path = Path(registry.__file__)
    return vars(registry), path


def _snapshot(namespace: dict) -> dict:
    return {name: dict(namespace.get(name, {})) for name in _REGISTRY_DICTS}


def _restore(namespace: dict, snapshot: dict) -> None:
    for name, entries in snapshot.items():
        namespace[name].clear()
        namespace[name].update(entries)


def _run_verification() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_registry.py", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output[-2000:]


def _delete_problem_row(db_path: Path, slug: str) -> None:
    """Remove a problem row the apply step just created (rollback only; the
    slug is guaranteed fresh, so no attempts can reference it)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM problems WHERE slug = ?", (slug,))
        conn.commit()


def apply(
    proposal: dict,
    *,
    problems_dir: Path = PROBLEMS_DIR,
    overrides_path: Path = PROBLEM_OVERRIDES,
    registry_path: Path | None = None,
    registry_namespace: dict | None = None,
    db_path: Path = DB_PATH,
    verify: Callable[[], tuple[bool, str]] = _run_verification,
) -> dict:
    """Write the proposal's artifacts, re-seed, and run the verification
    gate. Rolls everything back if the gate fails."""
    validate(proposal)
    if registry_namespace is None or registry_path is None:
        registry_namespace, registry_path = _default_registry_namespace()

    slug = proposal["slug"]
    registry_text = registry_path.read_text()
    overrides = json.loads(overrides_path.read_text())
    if slug in overrides:
        raise CuratorError(f"'{slug}' is already curated — pick a new slug")
    problem_path = problems_dir / proposal["pattern"] / f"{slug}.py"
    if problem_path.exists():
        raise CuratorError(f"problem file already exists: {problem_path}")

    # 1. Register the code in the live namespace (and validate it runs).
    namespace_snapshot = _snapshot(registry_namespace)
    for field in ("oracle_code", "judge_case_code", "checker_code", "profiler_code"):
        source = proposal.get(field)
        if not source:
            continue
        try:
            exec(compile(source, f"<curator {field}>", "exec"), registry_namespace)
        except Exception as exc:  # noqa: BLE001 - report, then abort
            _restore(registry_namespace, namespace_snapshot)
            raise CuratorError(f"{field} failed to execute: {exc}") from exc
    if slug not in registry_namespace["JUDGE_CASES"]:
        _restore(registry_namespace, namespace_snapshot)
        raise CuratorError("judge_case_code did not register a @judge_case for the slug")
    all_predicate = all("predicate" in c for c in proposal["visible_tests"])
    if slug not in registry_namespace["ORACLES"] and not all_predicate:
        _restore(registry_namespace, namespace_snapshot)
        raise CuratorError("no @oracle registered and the visible tests are not all predicate-checked")

    # 2. Write the artifacts.
    registry_block = "\n\n# --- curated by dojo curate: %s ---\n" % slug + "\n".join(
        proposal.get(field, "")
        for field in ("oracle_code", "judge_case_code", "checker_code", "profiler_code")
        if proposal.get(field)
    ) + "\n"
    overrides[slug] = {
        "function_name": proposal["function_name"],
        "signature": proposal["signature"],
        "visible_tests": proposal["visible_tests"],
    }
    try:
        problem_path.parent.mkdir(parents=True, exist_ok=True)
        problem_path.write_text(f'"""{proposal["statement"]}"""\n')
        overrides_path.write_text(json.dumps(overrides, indent=2) + "\n")
        registry_path.write_text(registry_text + registry_block)
        bank.seed_problems(connect(db_path), problems_dir)
    except Exception as exc:  # noqa: BLE001
        _restore(registry_namespace, namespace_snapshot)
        overrides_path.write_text(json.dumps(overrides, indent=2) + "\n")
        registry_path.write_text(registry_text)
        problem_path.unlink(missing_ok=True)
        _delete_problem_row(db_path, slug)
        raise CuratorError(f"apply failed: {exc}") from exc

    # 3. The acceptance gate.
    ok, output = verify()
    if not ok:
        _restore(registry_namespace, namespace_snapshot)
        overrides.pop(slug, None)
        overrides_path.write_text(json.dumps(overrides, indent=2) + "\n")
        registry_path.write_text(registry_text)
        problem_path.unlink(missing_ok=True)
        bank.seed_problems(connect(db_path), problems_dir)
        _delete_problem_row(db_path, slug)
        raise CuratorError(f"verification gate failed; rolled back.\n{output}")
    return {
        "slug": slug,
        "pattern": proposal["pattern"],
        "difficulty": proposal["difficulty"],
        "problem_file": str(problem_path),
        "verification": output or "verification passed",
    }
