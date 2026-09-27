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

NON_SERIALIZABLE = textwrap.dedent(
    """
    def is_valid(s: str) -> set:
        return {1, 2}
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
    """A crash is its own verdict, not a wrong answer (v0.13): `status` carries
    the judge's finding, and "my code raised" and "my logic is wrong" are
    different coaching problems. `error` used to be unreachable here."""
    report = run_cases(_write(tmp_path, CRASHING), "is_valid", CASES)
    assert report.status == "error"
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
    assert report.status == "error"
    assert report.results[0].error


def test_non_json_serializable_return_fails(tmp_path):
    """Strict JSON equality: a return value json.dumps can't serialize is a
    failed case with an error, never a lenient string-compare pass."""
    report = run_cases(_write(tmp_path, NON_SERIALIZABLE), "is_valid", CASES)
    assert report.status == "error"  # serialization is a harness-level failure
    assert all(not r.passed and r.error for r in report.results)


# ------------------------------------------------- "mutates" (in-place, v0.14)

ROTATE_CASES = [
    {"args": [[[1, 2], [3, 4]]], "expected": [[[3, 1], [4, 2]]], "compare": "mutates",
     "label": "2x2"},
    # 1x1 and 3x3, plus a case where nothing may happen but the shape
    {"args": [[[7]]], "expected": [[[7]]], "compare": "mutates", "label": "1x1"},
    {
        "args": [[[1, 2, 3], [4, 5, 6], [7, 8, 9]]],
        "expected": [[[7, 4, 1], [8, 5, 2], [9, 6, 3]]],
        "compare": "mutates",
        "label": "3x3",
    },
]

ROTATE_IN_PLACE = textwrap.dedent(
    """
    def rotate(matrix: list[list[int]]) -> None:
        matrix[:] = [list(row) for row in zip(*matrix[::-1])]
    """
)

ROTATE_REBINDING = textwrap.dedent(
    """
    def rotate(matrix: list[list[int]]) -> None:
        matrix = [list(row) for row in zip(*matrix[::-1])]  # returns nothing, changes nothing
    """
)

ROTATE_WRONG = textwrap.dedent(
    """
    def rotate(matrix: list[list[int]]) -> None:
        matrix.reverse()
    """
)


def test_in_place_solution_passes_a_mutates_case(tmp_path):
    report = run_cases(_write(tmp_path, ROTATE_IN_PLACE), "rotate", ROTATE_CASES)
    assert report.all_passed, report.results
    assert report.status == "correct"


def test_rebinding_without_mutating_fails_a_mutates_case(tmp_path):
    """The whole point of the mode: `matrix = <new list>` is not an in-place
    rotation, and the judge must not be fooled by a correct-looking value. (The
    1x1 case passes vacuously — rotating a single cell changes nothing.)"""
    report = run_cases(_write(tmp_path, ROTATE_REBINDING), "rotate", ROTATE_CASES)
    assert report.status == "wrong_answer"
    by_label = {r.label: r for r in report.results}
    assert not by_label["2x2"].passed
    assert not by_label["3x3"].passed


def test_a_mutates_failure_shows_the_arguments_not_none(tmp_path):
    """`got` is what the function produced. For an in-place problem that is the
    argument list as the call left it — reporting the None return beside an
    expected matrix reads as a dojo bug."""
    report = run_cases(_write(tmp_path, ROTATE_WRONG), "rotate", ROTATE_CASES)
    assert not report.all_passed
    first = report.results[0]
    assert first.got == [[[3, 4], [1, 2]]]  # reversed rows, not None
    assert first.expected == [[[3, 1], [4, 2]]]
