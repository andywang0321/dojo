"""Measurement + classification on real code: O(n) vs O(n^2).

The assertions here are deliberately coarse. A wall-clock test cannot pin an
exact class — that is what tests/test_fit.py does, on synthetic data — so
these check the honest property instead: the true class is either reported or
inside the reported bracket, and worse classes never appear.
"""

import textwrap

from dojo.judge.registry import PROFILER_INPUTS
from dojo.profiler import classify, measure
from dojo.profiler.measure import _run_once

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
    time_fit = classify(
        [n for n, _ in m.time_points], [t for _, t in m.time_points], spread=m.spread
    )
    space_fit = classify(
        [n for n, _ in m.space_points], [s for _, s in m.space_points], spread=m.spread
    )
    return time_fit, space_fit, m


def _claims(fit, expected: str) -> bool:
    """The honest property: the fit names the class, or the bracket contains
    it. Bracketing is a legitimate outcome; a confidently wrong class is not."""
    return fit.best_class == expected or expected in (fit.bracket or ())


def test_linear_solution_is_not_called_superlinear(tmp_path):
    """A textbook O(n) stack solution. The old, tracemalloc-contaminated
    measurement reported it confidently as O(n log n) — that is the regression
    this guards.

    The tracemalloc fix itself is pinned deterministically by the mechanism
    tests below, so this only asserts that nothing superlinear is *claimed*.
    Over a short ladder the signal is small next to the constant overhead, so
    the honest reading may be a bracket or even "flat" — that is the classifier
    being appropriately uncertain, not a failure. `best_class` is always the
    simplest plausible class, which is exactly why a superlinear value here
    would mean O(n) had been ruled out.
    """
    superlinear = ("O(n log n)", "O(n^2)", "O(n^3)")
    time_fit, space_fit, m = _profile(LINEAR, tmp_path, [100, 200, 400, 800, 1600, 3200])
    assert time_fit.best_class not in superlinear, (time_fit, m.time_points)
    assert space_fit.best_class not in superlinear, (space_fit, m.space_points)


def test_quadratic_solution_is_not_called_linear(tmp_path):
    """Real quadratic code must still be caught — bracketing must not swallow
    the distinctions that are actually identifiable."""
    time_fit, _, _ = _profile(QUADRATIC, tmp_path, [50, 100, 200, 400])
    assert time_fit.best_class != "O(n)", time_fit
    assert _claims(time_fit, "O(n^2)"), time_fit


# ------------------------------------------- instrument separation (v0.11)
#
# The regression: tracemalloc was started *before* the timed call, and its
# per-allocation bookkeeping is superlinear, so allocation-heavy O(n) code
# measured as O(n log n). These two tests pin the mechanism rather than a
# timing outcome, so they cannot flake.

TRACER_GUARD = textwrap.dedent(
    """
    import tracemalloc

    CALLS = 0

    def is_valid(s: str) -> bool:
        global CALLS
        CALLS += 1
        if CALLS == 2 and tracemalloc.is_tracing():
            raise RuntimeError("the timed call ran with tracemalloc active")
        return len(s) % 2 == 0
    """
)

INPLACE_GUARD = textwrap.dedent(
    """
    def is_valid(s: str) -> bool:
        chars = sorted(s)
        if list(s) == chars and len(s) > 1:
            raise RuntimeError("the input was already sorted: not a fresh copy")
        return True
    """
)


def test_timed_call_runs_without_the_tracer(tmp_path):
    """The second call inside the subprocess is the timed one, and no tracer
    may be running during it (v0.11)."""
    path = tmp_path / "solution.py"
    path.write_text(TRACER_GUARD)
    out = _run_once(path, "is_valid", ["()()"], timeout=20)
    assert out is not None, "the timed call ran with tracemalloc active"
    assert out["elapsed_ms"] > 0


def test_every_call_gets_a_fresh_copy(tmp_path):
    """Each call must see the original input: without a copy per call, the
    warm-up would leave the timed call a mutated (e.g. sorted) argument, and
    the measurement would describe a different job."""
    path = tmp_path / "solution.py"
    path.write_text(INPLACE_GUARD)
    out = _run_once(path, "is_valid", ["cba"], timeout=20)
    assert out is not None, "a later call saw a mutated argument"


def test_measurement_reports_its_own_spread(tmp_path):
    """The fit needs to know how noisy the run was; a silent spread of 0 would
    let it claim classes the data cannot support."""
    _, _, m = _profile(LINEAR, tmp_path, [100, 200, 400])
    assert m.spread >= 0.0
    assert isinstance(m.spread, float)


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
    """The real reported case: a set-based O(n)-space solution must not measure
    O(n^2) once the allocator staircase is un-aliased.

    `repeats=1` here means no repeat spread is available, so the classifier
    falls back to its systematic floor and may bracket — the regression this
    guards is the *aliasing*, which would make a quadratic the simplest
    plausible class."""
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
    fit = classify([n for n, _ in safe], [v for _, v in safe], spread=m.spread)
    assert fit.best_class not in ("O(n^2)", "O(n^3)"), (fit, m.space_points)
    assert _claims(fit, "O(n)"), (fit, m.space_points)
    assert fit.r2 > 0.9
