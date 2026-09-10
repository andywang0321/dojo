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


# --------------------------------------------------- allocator staircase (v0.8.1)

def test_staircase_sampling_aliases_and_the_fix():
    """Regression: a linear allocation whose size is a power-of-two
    staircase (Python set/dict tables) sampled at exact doublings aliases as
    O(n^2) — the reported contains_duplicate false flag. Fitting every
    second point (spacing x4) restores the honest O(n)."""
    from dojo.profiler.fit import staircase_safe_points

    sizes = [100, 200, 400, 800, 1600, 3200, 6400]
    values = [1, 1, 4, 4, 16, 16, 64]  # table steps x4, sampled x2 → paired plateaus

    aliased = classify(sizes, values)
    assert aliased.best_class == "O(n^2)"  # the bug, pinned (r² ≈ 0.97 — the live case)

    safe = staircase_safe_points(list(zip(sizes, values)))
    fixed = classify([n for n, _ in safe], [v for _, v in safe])
    assert fixed.best_class == "O(n)", fixed


def test_staircase_safe_keeps_smooth_series_intact():
    """The subsample must not distort smooth O(n) or genuine O(n^2) data —
    slopes 1 and 2 both survive doubling the spacing."""
    from dojo.profiler.fit import staircase_safe_points

    linear = list(zip([100, 200, 400, 800, 1600, 3200], [1, 2, 4, 8, 16, 32]))
    assert classify(*zip(*staircase_safe_points(linear))).best_class == "O(n)"

    quadratic = list(zip([100, 200, 400, 800, 1600, 3200], [1, 4, 16, 64, 256, 1024]))
    assert classify(*zip(*staircase_safe_points(quadratic))).best_class == "O(n^2)"


DUPLICATE_SET = textwrap.dedent(
    """
    def contains_duplicate(nums: list[int]) -> bool:
        return len(set(nums)) != len(nums)
    """
)


def test_hash_table_space_measures_linear(tmp_path):
    """The real reported case: a set-based O(n)-space solution must measure
    O(n), not O(n^2), once the allocator staircase is un-aliased."""
    from dojo.profiler.fit import staircase_safe_points

    path = tmp_path / "solution.py"
    path.write_text(DUPLICATE_SET)
    m = measure(
        path,
        "contains_duplicate",
        PROFILER_INPUTS["contains_duplicate"],
        sizes=[100, 200, 400, 800, 1600, 3200],
        repeats=1,
    )
    safe = staircase_safe_points(m.space_points)
    fit = classify([n for n, _ in safe], [v for _, v in safe])
    assert fit.best_class == "O(n)", (fit, m.space_points)
    assert fit.r2 > 0.9
