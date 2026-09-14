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
import random
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from dojo import bank
from dojo.config import DB_PATH, PROBLEMS_DIR, PROBLEM_OVERRIDES, REPO_ROOT
from dojo.db import connect
from dojo.judge.compare import check_equal
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

_REGISTRY_DICTS = ("ORACLES", "JUDGE_CASES", "REFERENCES", "PROFILER_INPUTS", "CHECKERS")


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
    for field in (
        "oracle_code",
        "judge_case_code",
        "reference_code",
        "checker_code",
        "profiler_code",
    ):
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

    return _propose_with(backend, CURATOR_SYSTEM, build_curator_prompt(statement, hints))


def _propose_with(backend, system: str, user: str) -> dict:
    raw = backend.chat_json(system, user)
    if "error" in raw:
        raise CuratorError(f"curator returned non-JSON: {raw['error']}")
    validate(raw)
    return raw


def make_isolated_namespace() -> dict:
    """A fresh registry namespace for executing curation code away from the
    live registries (tests and the dual-oracle differential check)."""
    ns = {
        "ORACLES": {},
        "JUDGE_CASES": {},
        "REFERENCES": {},
        "PROFILER_INPUTS": {},
        "CHECKERS": {},
        "random": __import__("random"),
        "math": __import__("math"),
    }

    def decorator(store):
        def make(name):
            def register(fn):
                store[name] = fn
                return fn

            return register

        return make

    ns["oracle"] = decorator(ns["ORACLES"])
    ns["judge_case"] = decorator(ns["JUDGE_CASES"])
    ns["reference"] = decorator(ns["REFERENCES"])
    ns["profiler_input"] = decorator(ns["PROFILER_INPUTS"])
    ns["checker"] = decorator(ns["CHECKERS"])
    return ns


def _exec_proposal(proposal: dict, namespace: dict) -> None:
    for field in (
        "oracle_code",
        "judge_case_code",
        "reference_code",
        "checker_code",
        "profiler_code",
    ):
        source = proposal.get(field)
        if source:
            exec(compile(source, f"<dual {field}>", "exec"), namespace)


def _strict_equal(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def differential_check(proposal_a: dict, proposal_b: dict) -> list[str]:
    """Cross-check two independent curator runs: their oracles must agree on
    the generated cases. Returns human-readable disagreements (empty = the
    two oracles agree)."""
    has_a = bool(proposal_a.get("oracle_code"))
    has_b = bool(proposal_b.get("oracle_code"))
    if has_a != has_b:
        return ["one proposal has an oracle and the other does not"]
    if not has_a:
        return []  # predicate-only problems have nothing to cross-check

    ns_a, ns_b = make_isolated_namespace(), make_isolated_namespace()
    try:
        _exec_proposal(proposal_a, ns_a)
        _exec_proposal(proposal_b, ns_b)
    except Exception as exc:  # noqa: BLE001
        return [f"a proposal's code failed to execute: {exc}"]
    slug = proposal_a["slug"]
    if slug not in ns_a["ORACLES"] or slug not in ns_a["JUDGE_CASES"]:
        return ["first proposal did not register oracle + generator"]
    if slug not in ns_b["ORACLES"]:
        return ["second proposal did not register an oracle"]

    disagreements = []
    for n in (0, 3, 7, 12):
        for seed in range(5):
            rng = random.Random(f"dual-{slug}-{n}-{seed}")
            generated = ns_a["JUDGE_CASES"][slug](n, rng)
            args, expected = generated[:2]
            extras = generated[2] if len(generated) > 2 else {}
            if extras.get("predicate"):
                continue  # checkers can't be cross-checked this way
            call_args = [extras["ops"]] if extras.get("ops") is not None else args
            got_a = ns_a["ORACLES"][slug](*call_args)
            got_b = ns_b["ORACLES"][slug](*call_args)
            if _strict_equal(got_a, expected) and _strict_equal(got_a, got_b):
                continue
            disagreements.append(
                f"n={n} seed={seed}: first={got_a!r} second={got_b!r} "
                f"expected={expected!r}"
            )
            if len(disagreements) >= 5:
                return disagreements
    return disagreements


def curate_dual(backend, statement: str, hints: dict | None = None) -> dict:
    """Two independent curator runs; the oracles must agree on the generated
    cases before either proposal is trusted (the oracle is the trust root)."""
    from dojo.curator.prompts import CURATOR_SYSTEM, build_curator_prompt

    user = build_curator_prompt(statement, hints)
    first = _propose_with(backend, CURATOR_SYSTEM, user)
    second_system = (
        CURATOR_SYSTEM
        + "\n\nThis is an independent second pass. Implement the oracle using "
        "a different construction or algorithm than before; the two oracles "
        "will be cross-checked against each other."
    )
    second = _propose_with(backend, second_system, user)
    disagreements = differential_check(first, second)
    if disagreements:
        raise CuratorError(
            "dual-oracle differential failed — the two curator runs disagree:\n"
            + "\n".join(disagreements)
        )
    return first


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


def _restore_problem_file(path: Path, original: str | None) -> None:
    """Rollback for the seed file: restore the pre-apply text, or remove the
    file if it did not exist before."""
    if original is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(original)


def _delete_problem_row(db_path: Path, slug: str) -> None:
    """Remove a problem row the apply step just created (rollback only; the
    slug is guaranteed fresh, so no attempts can reference it)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM problems WHERE slug = ?", (slug,))
        conn.commit()


def audit_curation(
    backend,
    statement: str,
    visible_tests: list,
    *,
    live_oracle=None,
    live_generator=None,
) -> dict:
    """Cross-check the live oracle against a fresh curator run, then let the
    audit agent reason about the prompt-vs-judge contract. Returns the audit
    JSON: {"findings": [...], "verdict": "ok"|"fix", "explanation": ...}."""
    from dojo.curator.prompts import AUDIT_SYSTEM, build_audit_prompt

    automated: list[str] = []
    try:
        fresh = propose(backend, statement)
        if live_oracle is not None and live_generator is not None and fresh.get("oracle_code"):
            ns = make_isolated_namespace()
            _exec_proposal(fresh, ns)
            slug = fresh["slug"]
            if slug in ns["ORACLES"] and slug in ns["JUDGE_CASES"]:
                for n in (0, 3, 7, 12):
                    for seed in range(5):
                        rng = random.Random(f"audit-{slug}-{n}-{seed}")
                        generated = live_generator(n, rng)
                        args, expected = generated[0], generated[1]
                        extras = generated[2] if len(generated) > 2 else {}
                        if extras.get("predicate"):
                            continue
                        call_args = [extras["ops"]] if extras.get("ops") is not None else args
                        if not _strict_equal(live_oracle(*call_args), ns["ORACLES"][slug](*call_args)):
                            automated.append(
                                f"n={n} seed={seed}: live oracle and fresh oracle disagree "
                                f"(live={live_oracle(*call_args)!r})"
                            )
                            break
                    if len(automated) >= 5:
                        break
    except CuratorError:
        automated.append("fresh curator run failed — cannot cross-check")

    audit = backend.chat_json(
        AUDIT_SYSTEM, build_audit_prompt(statement, visible_tests, automated)
    )
    if "error" in audit:
        raise CuratorError(f"auditor returned non-JSON: {audit['error']}")
    audit["automated_findings"] = automated
    return audit


def _module_view(namespace: dict):
    """A module-like view of an isolated namespace, so predicate checkers that
    reach for a sibling function (``module.decode(...)``) still work."""
    return SimpleNamespace(
        **{k: v for k, v in namespace.items() if not k.startswith("_")}
    )


def _case_findings(label, case, reference_fn, checkers, module_view) -> list[str]:
    args = case.get("args")
    if case.get("ops") is not None:
        args = [case["ops"]]  # class problems: the oracle takes the op list
    try:
        got = reference_fn(*(args or []))
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return [f"{label}: the reference raised {type(exc).__name__}: {exc}"]

    predicate = case.get("predicate")
    if predicate:
        checker = checkers.get(predicate)
        if checker is None:
            return [f"{label}: predicate '{predicate}' has no registered checker"]
        try:
            ok = bool(checker(module_view, got, case.get("args")))
        except Exception as exc:  # noqa: BLE001
            return [
                f"{label}: the '{predicate}' checker could not validate the "
                f"reference ({type(exc).__name__}: {exc})"
            ]
        return [] if ok else [f"{label}: the reference fails the '{predicate}' checker"]

    expected = case.get("expected")
    mode = case.get("compare", "strict")
    if not check_equal(got, expected, mode):
        return [f"{label}: the reference returned {got!r}, the case expects {expected!r}"]
    return []


def reference_findings(
    slug: str, namespace: dict, visible_tests: list[dict] | None = None
) -> list[str]:
    """The admission gate for a canonical reference (v0.12).

    A reference is worth exactly as much as its agreement with the trust anchor,
    so it is admitted only where the oracle can run: every visible test and every
    generated case, judged by the *judge's own* verdict modes (a predicate case
    goes through its checker). Returns human-readable findings; empty = admitted.

    ``namespace`` may be the isolated curation namespace or the live registry —
    both expose REFERENCES / ORACLES / JUDGE_CASES / CHECKERS.
    """
    reference_fn = namespace.get("REFERENCES", {}).get(slug)
    if reference_fn is None:
        return [f"no @reference('{slug}') was registered"]
    if namespace.get("ORACLES", {}).get(slug) is None:
        return [f"'{slug}' has no @oracle, so a reference cannot be gated against it"]

    cases = [(f"visible {i + 1}", case) for i, case in enumerate(visible_tests or [])]
    generator = namespace.get("JUDGE_CASES", {}).get(slug)
    if generator is not None:
        for n in (0, 3, 7, 12):
            for seed in range(5):
                rng = random.Random(f"ref-{slug}-{n}-{seed}")
                generated = generator(n, rng)
                args, expected = generated[:2]
                extras = generated[2] if len(generated) > 2 else {}
                cases.append(
                    (
                        f"generated n={n} seed={seed}",
                        {**extras, "args": args, "expected": expected},
                    )
                )

    checkers = namespace.get("CHECKERS", {})
    module_view = _module_view(namespace)
    findings: list[str] = []
    for label, case in cases:
        findings.extend(_case_findings(label, case, reference_fn, checkers, module_view))
        if len(findings) >= 5:
            break
    return findings


def _ensure_reference_registered(
    slug: str,
    source: str,
    namespace: dict,
    *,
    before_names: set[str],
    before_refs: set[str],
    function_name: str,
) -> tuple[str, str]:
    """Make ``source`` register a reference under ``slug``; return (source, note).

    Repairing shape variance here rather than failing follows the precedent of
    `reviewer.normalize_review`: the model returning a bare `def`, a different
    slug, or the class itself instead of the op-list driver is a formatting slip,
    and the response otherwise holds a good canonical solution.

    It is not hypothetical. All 48 reference proposals in the first live run came
    back undecorated — the prompt mentioned the decorator only as "already in
    scope" and never told the model the slug — so every problem was reported as
    failing a gate that had never compared anything. The file is the source of
    truth (a reference registered in memory but not decorated would vanish on the
    next import), so any repair is written into the returned source too.
    """
    import inspect

    if slug in namespace["REFERENCES"]:
        return source, ""

    # The model may have used a slug of its own invention; one fresh key is that.
    fresh = [k for k in namespace["REFERENCES"] if k not in before_refs]
    if len(fresh) == 1:
        namespace["REFERENCES"][slug] = namespace["REFERENCES"].pop(fresh[0])

    # Definitions this source added — the reliable discriminator, since the
    # decorators already in the namespace are names too.
    mine = [
        namespace[name]
        for name in namespace
        if name not in before_names
        and (inspect.isfunction(namespace[name]) or inspect.isclass(namespace[name]))
    ]
    entry = next((f for f in mine if f.__name__ == function_name), None)
    if entry is None and len(mine) == 1:
        entry = mine[0]
    if entry is None:
        raise CuratorError(
            f"the returned source defines no usable entry point for '{slug}' "
            f"({len(mine)} definition(s) found, none named '{function_name}') and did "
            f"not register @reference('{slug}')"
        )

    if inspect.isclass(entry):
        # A class problem (min_stack, and the design problems like it): the
        # oracle's convention is one argument — the [method, *args] op list — but
        # the natural thing to write, and what the student writes, is the class.
        # Drive it exactly the way the judge harness drives the student's class.
        wrapper = (
            f'\n\n@reference("{slug}")\n'
            f"def _{slug}_reference(ops: list[list]) -> list:\n"
            f"    instance = {entry.__name__}()\n"
            f"    out: list = []\n"
            f"    for op in ops:\n"
            f"        method, *args = op\n"
            f"        out.append(getattr(instance, method)(*args))\n"
            f"    return out\n"
        )
        exec(compile(wrapper, f"<reference wrapper {slug}>", "exec"), namespace)
        return source + wrapper, "the model returned a class — wrapped it in the op-list driver"

    namespace["REFERENCES"][slug] = entry

    lines = source.splitlines()
    index = entry.__code__.co_firstlineno - 1  # first decorator line, or the def
    decorated = re.fullmatch(r"\s*@reference\(\s*['\"][^'\"]*['\"]\s*\)\s*", lines[index])
    if decorated:
        lines[index] = f'@reference("{slug}")'
        note = "the returned decorator named a different slug — renamed"
    else:
        lines.insert(index, f'@reference("{slug}")')
        note = "the returned source had no decorator — added @reference(...)"
    return "\n".join(lines), note


def _source_or_none(fn) -> str | None:
    """The function's source, when Python can still find it.

    The oracle normally lives in a real file, but a registry can also be built
    dynamically (as the tests do). Showing the oracle to the reference writer is
    an aid — it pins the argument order and the canonical output order — not a
    requirement, so a missing source degrades to a prompt without it instead of
    crashing the command."""
    import inspect

    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return None


def add_reference(
    slug: str,
    backend,
    *,
    overrides_path: Path = PROBLEM_OVERRIDES,
    registry_path: Path | None = None,
    registry_namespace: dict | None = None,
    db_path: Path = DB_PATH,
    verify: Callable[[], tuple[bool, str]] = _run_verification,
    overwrite: bool = False,
) -> dict:
    """Generate, gate, and install the canonical reference for a curated problem.

    Nothing is written until the proposal has been proved equivalent to the
    oracle everywhere the oracle can run, so the common failure path needs no
    rollback: a reference that disagrees is simply refused.
    """
    from dojo.curator.prompts import REFERENCE_SYSTEM, build_reference_prompt

    if registry_namespace is None or registry_path is None:
        registry_namespace, registry_path = _default_registry_namespace()
    if slug in registry_namespace.get("REFERENCES", {}) and not overwrite:
        raise CuratorError(f"'{slug}' already has a reference — pass --force to replace it")

    with connect(db_path) as conn:
        problem = conn.execute("SELECT * FROM problems WHERE slug = ?", (slug,)).fetchone()
    if problem is None:
        raise CuratorError(f"unknown problem '{slug}'")
    if not problem["function_name"]:
        raise CuratorError(f"'{slug}' is not curated (no function_name)")
    oracle = registry_namespace.get("ORACLES", {}).get(slug)
    if oracle is None:
        raise CuratorError(
            f"'{slug}' has no @oracle in judge/registry.py — a reference can only be "
            "admitted against a brute-force anchor"
        )

    overrides = json.loads(overrides_path.read_text())
    entry = overrides.get(slug) or {}
    visible_tests = entry.get("visible_tests", [])
    raw = backend.chat_json(
        REFERENCE_SYSTEM,
        build_reference_prompt(
            slug,
            problem["statement"],
            problem["function_name"],
            entry.get("signature"),
            visible_tests,
            _source_or_none(oracle),
            problem["expected_time"],
            problem["expected_space"],
        ),
    )
    if "error" in raw:
        raise CuratorError(f"the reference writer returned non-JSON: {raw['error']}")
    source = (raw.get("reference_code") or "").strip()
    if not source:
        raise CuratorError("the reference writer returned no reference_code")
    try:
        compile(source, f"<reference {slug}>", "exec")
    except SyntaxError as exc:
        raise CuratorError(f"the reference does not compile: {exc}") from exc

    # Gate in an isolated namespace seeded with the live registries: the gate
    # needs the real oracle, and nothing may touch the live namespace until it
    # has passed.
    trial = make_isolated_namespace()
    for store in ("ORACLES", "JUDGE_CASES", "CHECKERS"):
        trial[store].update(registry_namespace.get(store, {}))
    before_names = set(trial)
    before_refs = set(trial["REFERENCES"])
    try:
        exec(compile(source, f"<reference {slug}>", "exec"), trial)
    except Exception as exc:  # noqa: BLE001
        raise CuratorError(f"the reference failed to execute: {exc}") from exc
    source, repair = _ensure_reference_registered(
        slug,
        source,
        trial,
        before_names=before_names,
        before_refs=before_refs,
        function_name=problem["function_name"],
    )
    findings = reference_findings(slug, trial, visible_tests)
    if findings:
        raise CuratorError(
            "the reference disagrees with the oracle — refused:\n" + "\n".join(findings)
        )

    registry_text = registry_path.read_text()
    snapshot = _snapshot(registry_namespace)
    block = f"\n\n# --- canonical reference ({slug}) ---\n{source}\n"
    try:
        exec(compile(source, f"<reference {slug}>", "exec"), registry_namespace)
        registry_path.write_text(registry_text + block)
    except Exception as exc:  # noqa: BLE001
        _restore(registry_namespace, snapshot)
        registry_path.write_text(registry_text)
        raise CuratorError(f"installing the reference failed: {exc}") from exc

    ok, output = verify()
    if not ok:
        _restore(registry_namespace, snapshot)
        registry_path.write_text(registry_text)
        raise CuratorError(f"verification gate failed; rolled back.\n{output}")
    note = raw.get("note", "")
    if repair:
        note = f"{note} ({repair})" if note else repair
    return {"slug": slug, "note": note, "verification": output or "verified"}


def apply(
    proposal: dict,
    *,
    problems_dir: Path = PROBLEMS_DIR,
    overrides_path: Path = PROBLEM_OVERRIDES,
    registry_path: Path | None = None,
    registry_namespace: dict | None = None,
    db_path: Path = DB_PATH,
    verify: Callable[[], tuple[bool, str]] = _run_verification,
    overwrite: bool = False,
) -> dict:
    """Write the proposal's artifacts, re-seed, and run the verification
    gate. Rolls everything back if the gate fails. ``overwrite`` re-curates
    an existing slug (the new registry block wins at import)."""
    validate(proposal)
    if registry_namespace is None or registry_path is None:
        registry_namespace, registry_path = _default_registry_namespace()

    slug = proposal["slug"]
    registry_text = registry_path.read_text()
    overrides = json.loads(overrides_path.read_text())
    original_overrides = dict(overrides)
    if slug in overrides and not overwrite:
        raise CuratorError(f"'{slug}' is already curated — pick a new slug")
    problem_path = problems_dir / proposal["pattern"] / f"{slug}.py"
    existing_problem_text = problem_path.read_text() if problem_path.exists() else None
    if problem_path.exists() and not overwrite:
        raise CuratorError(f"problem file already exists: {problem_path}")

    # 1. Register the code in the live namespace (and validate it runs).
    namespace_snapshot = _snapshot(registry_namespace)
    for field in (
        "oracle_code",
        "judge_case_code",
        "reference_code",
        "checker_code",
        "profiler_code",
    ):
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

    # 1b. A canonical reference is optional, but a wrong one is worse than none:
    # the probe would derive confident verdicts about the student from a broken
    # baseline. Gate it here, before anything is written, so a refusal needs no
    # rollback of files.
    if proposal.get("reference_code"):
        if slug not in registry_namespace["REFERENCES"]:
            _restore(registry_namespace, namespace_snapshot)
            raise CuratorError(
                "reference_code did not register a @reference for the slug"
            )
        findings = reference_findings(
            slug, registry_namespace, proposal["visible_tests"]
        )
        if findings:
            _restore(registry_namespace, namespace_snapshot)
            raise CuratorError(
                "the proposal's reference disagrees with its oracle — refused:\n"
                + "\n".join(findings)
            )

    # 2. Write the artifacts.
    registry_block = "\n\n# --- curated by dojo curate: %s ---\n" % slug + "\n".join(
        proposal.get(field, "")
        for field in (
            "oracle_code",
            "judge_case_code",
            "reference_code",
            "checker_code",
            "profiler_code",
        )
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
        overrides_path.write_text(json.dumps(original_overrides, indent=2) + "\n")
        registry_path.write_text(registry_text)
        _restore_problem_file(problem_path, existing_problem_text)
        _delete_problem_row(db_path, slug)
        raise CuratorError(f"apply failed: {exc}") from exc

    # 3. The acceptance gate.
    ok, output = verify()
    if not ok:
        _restore(registry_namespace, namespace_snapshot)
        overrides_path.write_text(json.dumps(original_overrides, indent=2) + "\n")
        registry_path.write_text(registry_text)
        _restore_problem_file(problem_path, existing_problem_text)
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
