"""Judge runner: correctness, crashes, and timeouts in the subprocess."""

import textwrap

from dojo.judge.runner import run_cases

CASES = [
    {"args": ["()"], "expected": True, "label": "ok1"},
    {"args": ["([)]"], "expected": False, "label": "ok2"},
    {"args": ["("], "expected": False, "label": "ok3"},
]

CORRECT = textwrap.dedent(
    """
    def is_valid(s: str) -> bool:
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in "([{":
                stack.append(ch)
            elif not stack or stack.pop() != pairs[ch]:
                return False
        return not stack
    """
)

WRONG = textwrap.dedent(
    """
    def is_valid(s: str) -> bool:
        return s.count("(") == s.count(")")
    """
)

CRASHING = textwrap.dedent(
    """
    def is_valid(s: str) -> bool:
        raise RuntimeError("boom")
    """
)

SLEEPING = textwrap.dedent(
    """
    import time
    def is_valid(s: str) -> bool:
        time.sleep(5)
        return True
    """
)


def _write(tmp_path, code):
    path = tmp_path / "solution.py"
    path.write_text(code)
    return path


def test_correct_solution_passes(tmp_path):
    report = run_cases(_write(tmp_path, CORRECT), "is_valid", CASES)
    assert report.all_passed
    assert report.passed == 3


def test_wrong_solution_reports_failures(tmp_path):
    report = run_cases(_write(tmp_path, WRONG), "is_valid", CASES)
    assert report.status == "wrong_answer"
    assert report.passed == 2  # "([)]" fails: counts match but order wrong


def test_crashing_solution_survives(tmp_path):
    report = run_cases(_write(tmp_path, CRASHING), "is_valid", CASES)
    assert report.status == "wrong_answer"
    assert all(r.error and "RuntimeError" in r.error for r in report.results)


def test_timeout_kills_the_subprocess(tmp_path):
    report = run_cases(_write(tmp_path, SLEEPING), "is_valid", CASES, timeout=0.5)
    assert report.status == "timed_out"


def test_import_error_is_reported(tmp_path):
    report = run_cases(
        _write(tmp_path, "def is_valid(x):\n    import not_a_real_module\n"),
        "is_valid",
        CASES,
    )
    assert report.status == "wrong_answer"
    assert report.results[0].error
