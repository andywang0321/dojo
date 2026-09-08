"""Curation contract: overrides ↔ registry all agree.

A problem is "curated" (✓ in `dojo list`) when it has function_name +
visible_tests + a template signature in `data/problem_overrides.json`, and a
judge-case generator plus an oracle (or predicate checkers) in
`judge/registry.py`. These tests pin that every curated slug's infrastructure
is complete and self-consistent — visible tests and generated cases agree
with the reference behavior, and representative references survive the real
judge subprocess protocol (strict, sorted, approx, predicate, and ops modes).
"""

import json
import random
import textwrap
from types import SimpleNamespace

from dojo.bank import load_overrides
from dojo.judge import CHECKERS, JUDGE_CASES, ORACLES, run_cases
from dojo.judge import registry as reg


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True)


def _equal(a, b) -> bool:
    """The judge's strict JSON equality."""
    return _canonical(a) == _canonical(b)


def _reference_module():
    """Reference encode/decode for the round-trip checker's contract tests."""

    def encode(strs: list[str]) -> str:
        return "".join(f"{len(s)}:{s}" for s in strs)

    def decode(s: str) -> list[str]:
        out, i = [], 0
        while i < len(s):
            j = s.index(":", i)
            n = int(s[i:j])
            out.append(s[j + 1 : j + 1 + n])
            i = j + 1 + n
        return out

    return SimpleNamespace(encode=encode, decode=decode)


def test_every_curated_slug_has_complete_infrastructure():
    overrides = load_overrides()
    slugs = set(overrides)
    assert slugs == set(JUDGE_CASES), f"judge-case mismatch: {sorted(slugs ^ set(JUDGE_CASES))}"
    for slug, entry in overrides.items():
        assert entry.signature, f"{slug}: missing template signature"
        has_oracle = slug in ORACLES
        all_predicate = bool(entry.visible_tests) and all(
            "predicate" in case for case in entry.visible_tests
        )
        assert has_oracle or all_predicate, (
            f"{slug}: no oracle and its visible tests are not all predicate-checked"
        )


def test_visible_tests_agree_with_references():
    ref_module = _reference_module()
    for slug, entry in load_overrides().items():
        for i, case in enumerate(entry.visible_tests):
            where = f"{slug} visible test {i + 1}"
            if "ops" in case:
                assert _equal(ORACLES[slug](case["ops"]), case["expected"]), where
            elif case.get("predicate") == "encode_decode_roundtrip":
                got = ref_module.encode(case["args"][0])
                assert CHECKERS["encode_decode_roundtrip"](ref_module, got, case["args"]), where
            elif case.get("predicate") == "sample_valid":
                sample = reg._reference_sample(*case["args"])
                assert CHECKERS["sample_valid"](None, sample, case["args"]), where
            elif case.get("predicate") == "is_peak":
                assert CHECKERS["is_peak"](None, ORACLES[slug](*case["args"]), case["args"]), where
            else:
                got = ORACLES[slug](*case["args"])
                assert _equal(got, case["expected"]), f"{where}: {got!r} vs {case['expected']!r}"


def test_generated_cases_agree_with_references():
    ref_module = _reference_module()
    for slug, generator in JUDGE_CASES.items():
        rng = random.Random(f"dojo-registry-{slug}")
        for n in (0, 3, 7, 12):
            generated = generator(n, rng)
            args, expected = generated[:2]
            extras = generated[2] if len(generated) > 2 else {}
            where = f"{slug} generated case (n={n})"
            if extras.get("predicate") == "encode_decode_roundtrip":
                got = ref_module.encode(args[0])
                assert CHECKERS["encode_decode_roundtrip"](ref_module, got, args), where
            elif extras.get("predicate") == "sample_valid":
                sample = reg._reference_sample(*args)
                assert CHECKERS["sample_valid"](None, sample, args), where
            elif extras.get("ops") is not None:
                assert _equal(ORACLES[slug](extras["ops"]), expected), where
            else:
                got = ORACLES[slug](*args)
                assert _equal(got, expected), f"{where}: {got!r} vs {expected!r}"


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


_WRAPPERS = {
    "min_stack": textwrap.dedent(
        """
        class MinStack:
            def __init__(self):
                self.stack = []
                self.mins = []

            def push(self, val: int) -> None:
                self.stack.append(val)
                self.mins.append(val if not self.mins else min(val, self.mins[-1]))

            def pop(self) -> None:
                self.stack.pop()
                self.mins.pop()

            def top(self) -> int:
                return self.stack[-1]

            def getMin(self) -> int:
                return self.mins[-1]
        """
    ),
    "encode_and_decode_strings": textwrap.dedent(
        """
        def encode(strs: list[str]) -> str:
            return "".join(f"{len(s)}:{s}" for s in strs)

        def decode(s: str) -> list[str]:
            out, i = [], 0
            while i < len(s):
                j = s.index(":", i)
                n = int(s[i:j])
                out.append(s[j + 1 : j + 1 + n])
                i = j + 1 + n
            return out
        """
    ),
    "generate_sample_to_target_sum": (
        "from dojo.judge.registry import _reference_sample\n\n"
        "def generate_sample(n, sigma, target):\n"
        "    return _reference_sample(n, sigma, target)\n"
    ),
}


def _solution_source(slug: str, function_name: str) -> str:
    if slug in _WRAPPERS:
        return _WRAPPERS[slug]
    return _oracle_wrapper(slug, function_name)


def test_references_survive_the_real_judge(tmp_path):
    """Representative output shapes through the actual subprocess judge:
    bool, int, list, list-of-lists, float, nested-list trees, predicate
    round-trips and samples, and class ops sequences."""
    overrides = load_overrides()
    for slug in (
        "valid_parentheses",
        "three_sum",
        "correlation",
        "binary_tree_diameter",
        "k_smallest_elem_matrix",
        "valid_sudoku",
        "two_sum",
        "min_stack",
        "encode_and_decode_strings",
        "generate_sample_to_target_sum",
        "peak_elements",
    ):
        entry = overrides[slug]
        path = tmp_path / f"{slug}.py"
        path.write_text(_solution_source(slug, entry.function_name))
        rng = random.Random(f"dojo-{slug}")
        cases = [
            {**case, "label": f"visible {i + 1}"}
            for i, case in enumerate(entry.visible_tests)
        ]
        for i in range(10):
            n = rng.randint(0, 12)
            generated = JUDGE_CASES[slug](n, rng)
            args, expected = generated[:2]
            extras = generated[2] if len(generated) > 2 else {}
            cases.append(
                {"args": args, "expected": expected, "label": f"gen {i + 1}", **extras}
            )
        report = run_cases(path, entry.function_name, cases)
        assert report.all_passed, f"{slug}: {report.status}; {report.results[:3]}"
