"""Judge + profiler robustness (v0.10.1): user prints, sys.exit, and
import-time prints must never crash dojo or corrupt the protocol channel."""

import textwrap

from dojo.judge import run_cases
from dojo.profiler import probe as probe_mod

CASES = [
    {"args": [3], "expected": 6, "label": "a"},
    {"args": [4], "expected": 8, "label": "b"},
]


def _judge(code: str):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.py"
        path.write_text(textwrap.dedent(code))
        return run_cases(path, "double", CASES)


def test_print_in_solution_does_not_corrupt_judge():
    report = _judge(
        """
        def double(n):
            print("debug: doubling", n)
            return n * 2
        """
    )
    assert report.status == "correct", report.results
    assert report.passed == 2
    printed = "\n".join(r.printed for r in report.results)
    assert "debug: doubling 3" in printed  # prints are captured, not discarded


def test_import_time_print_does_not_corrupt_judge():
    report = _judge(
        """
        print("module loaded")

        def double(n):
            return n * 2
        """
    )
    assert report.status == "correct", report.results


def test_sys_exit_is_a_case_error_not_a_crash():
    report = _judge(
        """
        import sys

        def double(n):
            if n == 4:
                sys.exit("boom")
            return n * 2
        """
    )
    assert report.status == "wrong_answer"
    results = {r.label: r for r in report.results}
    assert results["a"].passed is True
    assert "SystemExit" in results["b"].error


def test_print_in_solution_does_not_corrupt_measurement(tmp_path):
    path = tmp_path / "solution.py"
    path.write_text(
        textwrap.dedent(
            """
            def double(n):
                print("debug print from the measured function")
                return n * 2
            """
        )
    )
    result = probe_mod.run_probe(
        probe_mod.Target("yours", path, "double"),
        lambda n, rng: [n],
        sizes=[100, 200, 400],
        repeats=1,
    )
    # Prints go to stderr inside the probe harness, so the JSON channel stays
    # intact and every size still measures.
    assert [p.n for p in result.points] == [100, 200, 400]
    assert all(p.student.ok and p.student.ms > 0 for p in result.points)
