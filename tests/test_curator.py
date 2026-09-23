"""The curation pipeline: proposal validation and apply-with-rollback."""

import json
import random

import pytest

from dojo.bank import parse_problem_file
from dojo.curator import CuratorError, apply, propose, validate
from dojo.db import connect, init_db
from dojo.tutor.backend import MockBackend

CANNED_PROPOSAL = {
    "slug": "matrix_diagonal_sum",
    "title": "Matrix Diagonal Sum",
    "difficulty": "Easy",
    "pattern": "arrays_and_hashing",
    "statement": (
        "Matrix Diagonal Sum [Easy]\n\n"
        "Given an n x n integer matrix, return the sum of the elements on both "
        "diagonals. Do not count the center element twice when n is odd.\n\n"
        "Example 1:\nInput: [[1,2,3],[4,5,6],[7,8,9]]\nOutput: 25\n\n"
        "You should aim for a solution with O(n) time and O(1) space, where n "
        "is the number of rows.\n"
    ),
    "function_name": "diagonal_sum",
    "signature": "(matrix: list[list[int]]) -> int",
    "visible_tests": [
        {"args": [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]], "expected": 25},
        {"args": [[[5]]], "expected": 5},
        {"args": [[[1, 2], [3, 4]]], "expected": 10},
    ],
    "oracle_code": (
        "@oracle('matrix_diagonal_sum')\n"
        "def _matrix_diagonal_sum_oracle(matrix):\n"
        "    n = len(matrix)\n"
        "    total = sum(matrix[i][i] + matrix[i][n - 1 - i] for i in range(n))\n"
        "    return total - (matrix[n // 2][n // 2] if n % 2 else 0)\n"
    ),
    "judge_case_code": (
        "@judge_case('matrix_diagonal_sum')\n"
        "def _matrix_diagonal_sum_case(n, rng):\n"
        "    n = max(1, min(n, 12))\n"
        "    matrix = [[rng.randint(-5, 5) for _ in range(n)] for _ in range(n)]\n"
        "    return [matrix], _matrix_diagonal_sum_oracle(matrix)\n"
    ),
    "profiler_code": (
        "@profiler_input('matrix_diagonal_sum')\n"
        "def _matrix_diagonal_sum_profiler(n, rng):\n"
        "    side = max(1, int(n ** 0.5))\n"
        "    return [[[rng.randint(-5, 5) for _ in range(side)] for _ in range(side)]]\n"
    ),
}


def _make_namespace() -> dict:
    ns = {
        "ORACLES": {},
        "JUDGE_CASES": {},
        "REFERENCES": {},
        "PROFILER_INPUTS": {},
        "CHECKERS": {},
        "random": random,
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


@pytest.fixture()
def paths(tmp_path):
    problems_dir = tmp_path / "problems"
    overrides_path = tmp_path / "overrides.json"
    registry_path = tmp_path / "registry.py"
    problems_dir.mkdir(parents=True)
    overrides_path.write_text("{}\n")
    registry_path.write_text("# synthetic registry\n")
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    return problems_dir, overrides_path, registry_path, db_path


def test_validate_rejects_bad_proposals():
    with pytest.raises(CuratorError, match="missing fields"):
        validate({"slug": "x"})
    bad = dict(CANNED_PROPOSAL, slug="Not-Snake")
    with pytest.raises(CuratorError, match="bad slug"):
        validate(bad)
    bad = dict(CANNED_PROPOSAL, difficulty="Trivial")
    with pytest.raises(CuratorError, match="bad difficulty"):
        validate(bad)
    bad = dict(CANNED_PROPOSAL, pattern="quantum")
    with pytest.raises(CuratorError, match="bad pattern"):
        validate(bad)
    bad = dict(CANNED_PROPOSAL, statement="no header here\n\njust text")
    with pytest.raises(CuratorError, match="Title"):
        validate(bad)
    bad = dict(CANNED_PROPOSAL, signature="matrix -> int")
    with pytest.raises(CuratorError, match="signature"):
        validate(bad)
    bad = dict(CANNED_PROPOSAL, visible_tests=[{"args": []}])
    with pytest.raises(CuratorError, match="visible_tests"):
        validate(bad)
    bad = dict(CANNED_PROPOSAL, oracle_code="def broken(:\n")
    with pytest.raises(CuratorError, match="does not compile"):
        validate(bad)


def test_propose_returns_validated_proposal():
    proposal = propose(MockBackend(curator=CANNED_PROPOSAL), "some statement")
    assert proposal == CANNED_PROPOSAL


def test_curator_prompt_carries_fetcher_hints():
    from dojo.curator.prompts import build_curator_prompt

    prompt = build_curator_prompt(
        "Two Sum [Easy]\n\n...",
        hints={
            "function_name": "twoSum",
            "signature": "(nums: list[int], target: int) -> list[int]",
            "pattern": "arrays_and_hashing",
        },
    )
    assert "Starter-code hints" in prompt
    assert "function_name: twoSum" in prompt
    assert "pattern: arrays_and_hashing" in prompt
    assert "Two Sum [Easy]" in prompt


def test_apply_writes_artifacts_and_passes_gate(paths):
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    registry_text = registry_path.read_text()

    summary = apply(
        CANNED_PROPOSAL,
        problems_dir=problems_dir,
        overrides_path=overrides_path,
        registry_path=registry_path,
        registry_namespace=namespace,
        db_path=db_path,
        verify=lambda: (True, "all good"),
    )

    assert summary["slug"] == "matrix_diagonal_sum"
    problem_file = problems_dir / "arrays_and_hashing" / "matrix_diagonal_sum.py"
    assert parse_problem_file(problem_file) is not None
    overrides = json.loads(overrides_path.read_text())
    assert overrides["matrix_diagonal_sum"]["function_name"] == "diagonal_sum"
    assert overrides["matrix_diagonal_sum"]["signature"] == "(matrix: list[list[int]]) -> int"
    assert "@oracle('matrix_diagonal_sum')" in registry_path.read_text()
    assert registry_path.read_text().startswith(registry_text)  # append, not clobber
    assert "matrix_diagonal_sum" in namespace["ORACLES"]
    assert "matrix_diagonal_sum" in namespace["JUDGE_CASES"]
    assert "matrix_diagonal_sum" in namespace["PROFILER_INPUTS"]
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM problems WHERE slug='matrix_diagonal_sum'"
        ).fetchone()
    assert row is not None and row["pattern"] == "arrays_and_hashing"


def test_apply_rolls_back_when_gate_fails(paths):
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    registry_text = registry_path.read_text()

    with pytest.raises(CuratorError, match="verification gate failed"):
        apply(
            CANNED_PROPOSAL,
            problems_dir=problems_dir,
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (False, "boom"),
        )

    assert registry_path.read_text() == registry_text
    assert json.loads(overrides_path.read_text()) == {}
    assert not (problems_dir / "arrays_and_hashing" / "matrix_diagonal_sum.py").exists()
    assert "matrix_diagonal_sum" not in namespace["ORACLES"]
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM problems WHERE slug='matrix_diagonal_sum'"
        ).fetchone()
    assert row is None


def test_apply_rolls_back_when_generated_code_crashes(paths):
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    registry_text = registry_path.read_text()
    proposal = dict(
        CANNED_PROPOSAL,
        judge_case_code=(
            "@judge_case('matrix_diagonal_sum')\n"
            "def _broken(n, rng):\n"
            "    return []\n"
            "1 / 0  # top-level crash: exec must surface it\n"
        ),
    )

    with pytest.raises(CuratorError, match="failed to execute"):
        apply(
            proposal,
            problems_dir=problems_dir,
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (True, "unused"),
        )

    assert registry_path.read_text() == registry_text
    assert json.loads(overrides_path.read_text()) == {}


# --------------------------------------------------- dual-oracle differential

CANNED_ALT = {
    **CANNED_PROPOSAL,
    "oracle_code": (
        "@oracle('matrix_diagonal_sum')\n"
        "def _alt_diagonal_oracle(matrix):\n"
        "    n = len(matrix)\n"
        "    total = sum(matrix[i][i] for i in range(n))\n"
        "    total += sum(matrix[i][n - 1 - i] for i in range(n))\n"
        "    return total - (matrix[n // 2][n // 2] if n % 2 else 0)\n"
    ),
}

CANNED_DISAGREE = {
    **CANNED_PROPOSAL,
    "oracle_code": (
        "@oracle('matrix_diagonal_sum')\n"
        "def _wrong_diagonal_oracle(matrix):\n"
        "    return 0  # always wrong except for zero matrices\n"
    ),
}

CANNED_NO_ORACLE = {
    **CANNED_PROPOSAL,
    "oracle_code": "",
    "visible_tests": [
        {"args": [[[1]]], "predicate": "sample_valid", "expected": True},
        {"args": [[[2]]], "predicate": "sample_valid", "expected": True},
        {"args": [[[3]]], "predicate": "sample_valid", "expected": True},
    ],
}


def test_dual_oracle_agrees_and_returns_first_proposal():
    from dojo.curator import curate_dual

    backend = MockBackend(curator=[CANNED_PROPOSAL, CANNED_ALT])
    proposal = curate_dual(backend, "some statement")
    assert proposal == CANNED_PROPOSAL


def test_dual_oracle_disagrees_and_rejects():
    from dojo.curator import curate_dual

    backend = MockBackend(curator=[CANNED_PROPOSAL, CANNED_DISAGREE])
    with pytest.raises(CuratorError, match="differential"):
        curate_dual(backend, "some statement")


def test_dual_oracle_requires_both_sides():
    from dojo.curator import curate_dual

    backend = MockBackend(curator=[CANNED_PROPOSAL, CANNED_NO_ORACLE])
    with pytest.raises(CuratorError, match="differential"):
        curate_dual(backend, "some statement")


def test_dual_oracle_skips_predicate_only_pairs():
    from dojo.curator import curate_dual

    backend = MockBackend(curator=[CANNED_NO_ORACLE, dict(CANNED_NO_ORACLE)])
    proposal = curate_dual(backend, "some statement")
    assert proposal["slug"] == "matrix_diagonal_sum"


# ------------------------------------------------------------------- report


def test_audit_curation_detects_live_fresh_disagreement():
    from dojo.curator.curator import _exec_proposal, audit_curation, make_isolated_namespace

    ns = make_isolated_namespace()
    _exec_proposal(CANNED_PROPOSAL, ns)
    live_oracle = ns["ORACLES"]["matrix_diagonal_sum"]
    live_generator = ns["JUDGE_CASES"]["matrix_diagonal_sum"]

    backend = MockBackend(
        curator=[CANNED_DISAGREE],
        auditor={"findings": ["ties graded by equality"], "verdict": "fix", "explanation": "…"},
    )
    audit = audit_curation(
        backend,
        CANNED_PROPOSAL["statement"],
        CANNED_PROPOSAL["visible_tests"],
        live_oracle=live_oracle,
        live_generator=live_generator,
    )
    assert audit["verdict"] == "fix"
    assert any("disagree" in f for f in audit["automated_findings"])
    assert "ties graded by equality" in audit["findings"]


def test_audit_curation_clean_when_oracles_agree():
    from dojo.curator.curator import _exec_proposal, audit_curation, make_isolated_namespace

    ns = make_isolated_namespace()
    _exec_proposal(CANNED_PROPOSAL, ns)
    backend = MockBackend(curator=[CANNED_ALT])
    audit = audit_curation(
        backend,
        CANNED_PROPOSAL["statement"],
        CANNED_PROPOSAL["visible_tests"],
        live_oracle=ns["ORACLES"]["matrix_diagonal_sum"],
        live_generator=ns["JUDGE_CASES"]["matrix_diagonal_sum"],
    )
    assert audit["verdict"] == "ok"
    assert audit["automated_findings"] == []


def test_apply_overwrite_replaces_existing(paths):
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    existing_file = problems_dir / "arrays_and_hashing" / "matrix_diagonal_sum.py"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text('"""old statement"""\n')
    overrides_path.write_text(
        json.dumps(
            {
                "matrix_diagonal_sum": {
                    "function_name": "old_fn",
                    "signature": "(x) -> int",
                    "visible_tests": [],
                }
            }
        )
    )

    summary = apply(
        CANNED_PROPOSAL,
        problems_dir=problems_dir,
        overrides_path=overrides_path,
        registry_path=registry_path,
        registry_namespace=namespace,
        db_path=db_path,
        verify=lambda: (True, "ok"),
        overwrite=True,
    )
    assert summary["slug"] == "matrix_diagonal_sum"
    assert json.loads(overrides_path.read_text())["matrix_diagonal_sum"]["function_name"] == "diagonal_sum"
    assert "old statement" not in existing_file.read_text()
    assert "@oracle('matrix_diagonal_sum')" in registry_path.read_text()


def test_apply_overwrite_rolls_back_to_original(paths):
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    existing_file = problems_dir / "arrays_and_hashing" / "matrix_diagonal_sum.py"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text('"""old statement"""\n')
    original_overrides = {
        "matrix_diagonal_sum": {
            "function_name": "old_fn",
            "signature": "(x) -> int",
            "visible_tests": [],
        }
    }
    overrides_path.write_text(json.dumps(original_overrides))
    registry_text = registry_path.read_text()

    with pytest.raises(CuratorError, match="verification gate failed"):
        apply(
            CANNED_PROPOSAL,
            problems_dir=problems_dir,
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (False, "boom"),
            overwrite=True,
        )
    assert json.loads(overrides_path.read_text()) == original_overrides
    assert existing_file.read_text() == '"""old statement"""\n'
    assert registry_path.read_text() == registry_text


# ----------------------------------- references through the curate pipeline


#: The canonical single-pass form of the canned problem (both diagonals, the
#: centre counted once) — it must agree with the canned oracle exactly, which is
#: what the gate checks.
REFERENCE_CODE = '''
@reference("matrix_diagonal_sum")
def _diagonal_reference(matrix: list[list[int]]) -> int:
    size = len(matrix)
    total = 0
    for i in range(size):
        total += matrix[i][i] + matrix[i][size - 1 - i]
    if size % 2:
        total -= matrix[size // 2][size // 2]
    return total
'''

WRONG_REFERENCE_CODE = '''
@reference("matrix_diagonal_sum")
def _diagonal_reference(matrix: list[list[int]]) -> int:
    return 0
'''


def test_apply_installs_a_curator_reference(paths):
    """A proposal that carries a reference must actually install it.

    The probe measures every future attempt of this problem against that
    baseline, so a silently dropped reference is as bad as a wrong one."""
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    proposal = dict(CANNED_PROPOSAL, reference_code=REFERENCE_CODE)

    summary = apply(
        proposal,
        problems_dir=problems_dir,
        overrides_path=overrides_path,
        registry_path=registry_path,
        registry_namespace=namespace,
        db_path=db_path,
        verify=lambda: (True, "all good"),
    )

    assert summary["slug"] == "matrix_diagonal_sum"
    assert "matrix_diagonal_sum" in namespace["REFERENCES"]
    assert "@reference" in registry_path.read_text()


def test_apply_refuses_a_disagreeing_reference_before_writing(paths):
    """A wrong reference is worse than a missing one. The gate runs before any
    file is touched, so the refusal leaves nothing to roll back."""
    problems_dir, overrides_path, registry_path, db_path = paths
    namespace = _make_namespace()
    registry_before = registry_path.read_text()
    overrides_before = overrides_path.read_text()

    with pytest.raises(CuratorError, match="reference disagrees with its oracle"):
        apply(
            dict(CANNED_PROPOSAL, reference_code=WRONG_REFERENCE_CODE),
            problems_dir=problems_dir,
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (True, "all good"),
        )

    assert registry_path.read_text() == registry_before
    assert overrides_path.read_text() == overrides_before
    assert not (problems_dir / "arrays_and_hashing" / "matrix_diagonal_sum.py").exists()
    assert "matrix_diagonal_sum" not in namespace["REFERENCES"]
    assert "matrix_diagonal_sum" not in namespace["ORACLES"]



def test_the_curator_prompt_taxonomy_is_the_validated_taxonomy():
    """The prompt used to enumerate the pre-v0.10 taxonomy (dynamic_programming,
    math, graph — nine items) while `validate` enforced the 18 NeetCode slugs, so
    `dojo curate` was broken for dp/math problems and could only *mis-bucket* the
    rest. One source of truth, and this pins that it is used."""
    from dojo.curator.prompts import CURATOR_SYSTEM
    from dojo.patterns import PATTERNS

    enum_line = CURATOR_SYSTEM.split('- "pattern": one of (the dojo taxonomy')[1]
    enum_line = enum_line.split("\n")[0]
    for pattern in PATTERNS:
        assert pattern in enum_line, f"{pattern} missing from the curator prompt"
    for stale in ("dynamic_programming", "math,", "graph,"):
        assert stale not in enum_line.split("— pick")[0]


# ------------------------------------------------- the shape-repair boundary
# A live session died here (2026-09-23): the curator read the prompt's import
# rule as an instruction to write `from decorators import oracle`, and the
# ModuleNotFoundError escaped `audit_curation` as a traceback out of run_day.


DECORATOR_IMPORT_PROPOSAL = {
    **CANNED_PROPOSAL,
    "oracle_code": (
        "import math\n"
        "from decorators import oracle\n"
        "from typing import List\n"
        "\n"
        "@oracle('matrix_diagonal_sum')\n"
        "def _importing_oracle(matrix):\n"
        "    n = len(matrix)\n"
        "    total = sum(matrix[i][i] + matrix[i][n - 1 - i] for i in range(n))\n"
        "    return total - (matrix[n // 2][n // 2] if n % 2 else 0)\n"
    ),
    "judge_case_code": (
        "from decorators import judge_case\n"
        "\n"
        "@judge_case('matrix_diagonal_sum')\n"
        "def _case(n, rng):\n"
        "    side = max(1, min(n, 12))\n"
        "    matrix = [[rng.randint(-5, 5) for _ in range(side)] for _ in range(side)]\n"
        "    return [matrix], _importing_oracle(matrix)\n"
    ),
}


def test_sanitize_imports_drops_only_what_cannot_resolve():
    """The decorators are injected into the namespace, so an import for them
    can only fail; a real module import is somebody's legitimate tool."""
    from dojo.curator.curator import sanitize_imports

    source = (
        "import random\n"
        "from decorators import oracle\n"
        "import heapq\n"
        "from collections import deque\n"
        "from typing import List\n"
        "\n"
        "@oracle('x')\n"
        "def f(a, b):\n"
        "    return a + b\n"
    )
    repaired, dropped = sanitize_imports(source)
    assert dropped == ["from decorators import oracle"]
    assert "import heapq" in repaired and "from collections import deque" in repaired
    assert "List" in repaired and "import random" in repaired
    # Line numbers survive the repair: a traceback inside the snippet still
    # points at the right line.
    assert repaired.splitlines()[0] == "import random"
    assert repaired.splitlines()[2] == "import heapq"
    compile(repaired, "<repaired>", "exec")


def test_sanitize_imports_is_a_no_op_for_clean_code():
    from dojo.curator.curator import sanitize_imports

    source = CANNED_PROPOSAL["oracle_code"]
    assert sanitize_imports(source) == (source, [])


def test_sanitize_imports_leaves_broken_syntax_for_validate():
    from dojo.curator.curator import sanitize_imports

    source = "from decorators import oracle\ndef broken(:\n"
    assert sanitize_imports(source) == (source, [])  # validate reports it


def test_propose_repairs_a_decorator_import_and_says_so():
    proposal = propose(MockBackend(curator=DECORATOR_IMPORT_PROPOSAL), "some statement")
    assert "from decorators import" not in proposal["oracle_code"]
    assert "from decorators import" not in proposal["judge_case_code"]
    assert proposal["_repairs"] == [
        "oracle_code: from decorators import oracle",
        "judge_case_code: from decorators import judge_case",
    ]
    # The repair is what makes the artifact set executable.
    from dojo.curator.curator import _exec_proposal, make_isolated_namespace

    ns = make_isolated_namespace()
    _exec_proposal(proposal, ns)
    assert "matrix_diagonal_sum" in ns["ORACLES"]
    assert "matrix_diagonal_sum" in ns["JUDGE_CASES"]


def test_propose_leaves_repairs_absent_when_nothing_was_repaired():
    proposal = propose(MockBackend(curator=CANNED_PROPOSAL), "some statement")
    assert "_repairs" not in proposal


def test_exec_proposal_raises_curator_error_not_module_error():
    """The boundary that keeps a bad proposal from killing a session."""
    from dojo.curator.curator import _exec_proposal, make_isolated_namespace

    with pytest.raises(CuratorError, match="oracle_code failed to execute"):
        _exec_proposal(
            {"oracle_code": "raise RuntimeError('curator wrote nonsense')\n"},
            make_isolated_namespace(),
        )


def test_audit_curation_survives_a_proposal_that_cannot_execute():
    """The live crash: the fresh run's code raised out of the cross-check.

    The live registration has to be present, or the cross-check — and with it
    the exec of the fresh proposal — never runs. That is why this bug reached a
    student's session instead of failing in some offline path."""
    from dojo.curator.curator import _exec_proposal, audit_curation, make_isolated_namespace

    ns = make_isolated_namespace()
    _exec_proposal(CANNED_PROPOSAL, ns)
    backend = MockBackend(curator={**CANNED_PROPOSAL, "oracle_code": "raise SystemError('boom')\n"})
    audit = audit_curation(
        backend,
        CANNED_PROPOSAL["statement"],
        CANNED_PROPOSAL["visible_tests"],
        live_oracle=ns["ORACLES"]["matrix_diagonal_sum"],
        live_generator=ns["JUDGE_CASES"]["matrix_diagonal_sum"],
    )
    assert any(
        "fresh curator run failed" in f for f in audit["automated_findings"]
    ), audit["automated_findings"]
    assert audit["verdict"] == "ok"  # the auditor still ran and answered


def test_audit_curation_reports_a_stripped_import_as_a_finding():
    from dojo.curator.curator import audit_curation

    backend = MockBackend(curator=DECORATOR_IMPORT_PROPOSAL)
    audit = audit_curation(
        backend, CANNED_PROPOSAL["statement"], CANNED_PROPOSAL["visible_tests"]
    )
    assert any(
        "cannot resolve" in f and "from decorators import" in f
        for f in audit["automated_findings"]
    ), audit["automated_findings"]


def test_audit_curation_carries_the_student_note_into_the_prompt():
    """The optional comment is evidence for the auditor, not a verdict."""
    from dojo.curator.curator import audit_curation
    from dojo.tutor.backend import Role

    seen: dict[str, str] = {}
    backend = MockBackend(curator=CANNED_PROPOSAL)
    real_chat_json = backend.chat_json

    def capture(role, system, user, **kwargs):
        if role == Role.CURATION_AUDITOR:
            seen["prompt"] = user
        return real_chat_json(role, system, user, **kwargs)

    backend.chat_json = capture
    note = "the generated arrays are not sorted, so O(n) is unachievable"
    audit = audit_curation(
        backend,
        CANNED_PROPOSAL["statement"],
        CANNED_PROPOSAL["visible_tests"],
        note=note,
    )
    assert note in seen["prompt"]
    assert "WHAT THE STUDENT REPORTED" in seen["prompt"]
    assert audit["student_note"] == note


def test_audit_prompt_omits_the_note_block_when_there_is_none():
    from dojo.curator.prompts import build_audit_prompt

    assert "WHAT THE STUDENT REPORTED" not in build_audit_prompt("stmt", [], [])
    assert "WHAT THE STUDENT REPORTED" not in build_audit_prompt("stmt", [], [], "   ")


def test_audit_system_tells_the_auditor_a_student_can_be_wrong():
    """A report is a claim: the useful answer for a mistaken one is 'no'."""
    from dojo.curator.prompts import AUDIT_SYSTEM, build_audit_prompt

    assert "possibly mistaken" in build_audit_prompt("stmt", [], [], "a claim")
    assert "never invent a finding to agree with a student" in AUDIT_SYSTEM


def test_the_curator_prompt_forbids_importing_the_decorators():
    """The wording that caused the crash: it used to invite exactly the import
    that cannot resolve ("may import only: random, math, and the decorators")."""
    from dojo.curator.prompts import CURATOR_SYSTEM, REFERENCE_SYSTEM

    for prompt in (CURATOR_SYSTEM, REFERENCE_SYSTEM):
        assert "decorators" in prompt  # named, so the model can avoid it
        assert "no module named `decorators` exists" in prompt
