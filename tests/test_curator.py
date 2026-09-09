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
