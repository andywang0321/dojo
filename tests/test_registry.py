"""Curation contract: overrides ↔ signatures ↔ registry all agree.

A problem is only "curated" (✓ in `dojo list`) when it has function_name +
visible_tests, a template signature, and a judge-case generator + oracle.
These tests pin that every curated slug's infrastructure is complete and
self-consistent — visible tests agree with the oracle, generated cases agree
with the oracle, and a few representative oracles survive the real judge
subprocess protocol.
"""

import json
import random
import textwrap

from dojo.bank import load_overrides
from dojo.judge import JUDGE_CASES, ORACLES
from dojo.judge.runner import run_cases
from dojo.session.flow import SIGNATURES


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True)


def _equal(a, b) -> bool:
    """The judge's strict JSON equality."""
    return _canonical(a) == _canonical(b)


def test_every_curated_slug_has_complete_infrastructure():
    overrides = load_overrides()
    slugs = set(overrides)
    assert slugs == set(SIGNATURES), (
        "signature mismatch: "
        f"{sorted(slugs ^ set(SIGNATURES))}"
    )
    assert slugs == set(ORACLES), (
        "oracle mismatch: " f"{sorted(slugs ^ set(ORACLES))}"
    )
    assert slugs == set(JUDGE_CASES), (
        "judge-case mismatch: " f"{sorted(slugs ^ set(JUDGE_CASES))}"
    )


def test_visible_tests_agree_with_oracles():
    for slug, entry in load_overrides().items():
        oracle = ORACLES[slug]
        for i, case in enumerate(entry.visible_tests):
            got = oracle(*case["args"])
            assert _equal(got, case["expected"]), (
                f"{slug} visible test {i + 1}: oracle says {got!r}, "
                f"override says {case['expected']!r}"
            )


def test_generated_cases_agree_with_oracles():
    for slug, generator in JUDGE_CASES.items():
        oracle = ORACLES[slug]
        rng = random.Random(f"dojo-registry-{slug}")
        for n in (0, 3, 7, 12):
            args, expected = generator(n, rng)
            got = oracle(*args)
            assert _equal(got, expected), (
                f"{slug} generated case (n={n}): oracle says {got!r}, "
                f"generator says {expected!r}"
            )


def test_profiler_inputs_match_curated_slugs_and_scale():
    from dojo.judge import PROFILER_INPUTS

    assert set(PROFILER_INPUTS) <= set(load_overrides())
    rng = random.Random("profiler-sanity")

    # Matrix problems scale the side length so total elements ~= n.
    args = PROFILER_INPUTS["k_smallest_elem_matrix"](400, rng)
    assert len(args[1]) * len(args[1][0]) == 400

    # Tree problems build ~n nodes.
    def count(node) -> int:
        return 0 if node is None else 1 + count(node[1]) + count(node[2])

    args = PROFILER_INPUTS["binary_tree_diameter"](200, rng)
    assert count(args[0]) == 200

    # Plain linear problems produce an input of size n.
    assert len(PROFILER_INPUTS["contains_duplicate"](100, rng)[0]) == 100
    assert len(PROFILER_INPUTS["daily_temperatures"](100, rng)[0]) == 100


def _oracle_wrapper(slug: str, function_name: str) -> str:
    return (
        "from dojo.judge.registry import ORACLES\n\n"
        f"def {function_name}(*args):\n"
        f"    return ORACLES[{slug!r}](*args)\n"
    )


def test_oracle_wrappers_survive_the_real_judge(tmp_path):
    """Representative output shapes through the actual subprocess judge:
    bool, int, list, list-of-lists, float, and nested-list trees."""
    overrides = load_overrides()
    for slug in (
        "valid_parentheses",
        "three_sum",
        "correlation",
        "binary_tree_diameter",
        "k_smallest_elem_matrix",
        "valid_sudoku",
        "two_sum",
    ):
        entry = overrides[slug]
        path = tmp_path / f"{slug}.py"
        path.write_text(textwrap.dedent(_oracle_wrapper(slug, entry.function_name)))
        rng = random.Random(f"dojo-{slug}")
        cases = [
            {**case, "label": f"visible {i + 1}"}
            for i, case in enumerate(entry.visible_tests)
        ]
        for i in range(10):
            n = rng.randint(0, 12)
            args, expected = JUDGE_CASES[slug](n, rng)
            cases.append({"args": args, "expected": expected, "label": f"gen {i + 1}"})
        report = run_cases(path, entry.function_name, cases)
        assert report.all_passed, f"{slug}: {report.status}; {report.results[:3]}"
