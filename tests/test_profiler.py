"""Measurement + classification on real code: O(n) vs O(n^2)."""

import textwrap

from dojo.judge.registry import PROFILER_INPUTS
from dojo.profiler import classify, measure

LINEAR = textwrap.dedent(
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

QUADRATIC = textwrap.dedent(
    """
    def is_valid(s: str) -> bool:
        # Genuinely quadratic: repeatedly scan the whole string for an
        # adjacent pair and delete it. O(n) passes x O(n) scan per pass.
        # (NB: the naive `acc = acc[:-1]` string rebuild is NOT quadratic in
        # CPython 3.12+ — unshared strings resize in place.)
        chars = list(s)
        while True:
            changed = False
            for pair in ("()", "[]", "{}"):
                for i in range(len(chars) - 1):
                    if chars[i] == pair[0] and chars[i + 1] == pair[1]:
                        del chars[i:i + 2]
                        changed = True
                        break
                if changed:
                    break
            if not changed:
                break
        return not chars
    """
)


def _profile(code: str, tmp_path, sizes):
    path = tmp_path / "solution.py"
    path.write_text(code)
    m = measure(
        path,
        "is_valid",
        PROFILER_INPUTS["valid_parentheses"],
        sizes=sizes,
        repeats=2,
    )
    time_fit = classify([n for n, _ in m.time_points], [t for _, t in m.time_points])
    space_fit = classify([n for n, _ in m.space_points], [s for _, s in m.space_points])
    return time_fit, space_fit, m


def test_linear_solution_measures_linear(tmp_path):
    time_fit, space_fit, m = _profile(LINEAR, tmp_path, [100, 200, 400, 800, 1600])
    assert time_fit.best_class == "O(n)", (time_fit, m.time_points)
    assert space_fit.best_class == "O(n)", (space_fit, m.space_points)


def test_quadratic_solution_measures_quadratic(tmp_path):
    time_fit, _, _ = _profile(QUADRATIC, tmp_path, [50, 100, 200, 400])
    assert time_fit.best_class in ("O(n^2)", "O(n^3)"), time_fit
    assert time_fit.loglog_slope is None or time_fit.loglog_slope > 1.3
