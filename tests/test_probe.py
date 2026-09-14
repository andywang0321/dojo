"""The scale probe: what it reports, and the mechanism that keeps it honest.

Two kinds of test here, and deliberately nothing in between:

- **Mechanism tests** pin the things that are true by construction — the timed
  window has no tracer in it and no argument copy, a failure is reported rather
  than swallowed. These cannot flake.
- **Synthetic tests** drive the pairing logic with a fake generator, so the
  ratios and verdicts are exact.

No test asserts a complexity class from wall-clock timing. That was the v0.11
mistake: it tests the machine's load, not the code.
"""

import random
import textwrap

import pytest

from dojo.profiler import growth
from dojo.profiler.probe import (
    Probe,
    Run,
    ScalePoint,
    Target,
    ladder,
    run_one,
    run_probe,
)

LINEAR = "def f(a):\n    t = 0\n    for x in a:\n        t += x\n    return t\n"
CONSTANT = "def f(a):\n    return 42\n"
RAISES_ABOVE = textwrap.dedent(
    """
    def f(a):
        if len(a) > 250:
            raise ValueError("Not enough elements!")
        return len(a)
    """
)
TRACER_GUARD = textwrap.dedent(
    """
    import tracemalloc

    CALLS = 0

    def f(a):
        global CALLS
        CALLS += 1
        if CALLS == 2 and tracemalloc.is_tracing():
            raise RuntimeError("the timed call ran with tracemalloc active")
        return len(a)
    """
)
INPLACE_GUARD = textwrap.dedent(
    """
    def f(a):
        ordered = sorted(a)
        if list(a) == ordered and len(a) > 1:
            raise RuntimeError("the input was already sorted: not a fresh copy")
        return len(ordered)
    """
)
SLOW = "def f(a):\n    import time\n    time.sleep(30)\n    return len(a)\n"


def _write(tmp_path, name, source):
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    return path


def _ints(n, rng):
    return [list(range(n))]


# ------------------------------------------------------------- mechanism


def test_a_constant_work_function_measures_flat(tmp_path):
    """Regression for the v0.11 copy-inside-the-window bug.

    A function that ignores its input costs the same at every size, so the
    *absolute* time is the sharp discriminator: measured on an idle machine this
    sits at 0.1-0.2 microseconds, while one `deepcopy` of the n=6400 argument
    takes ~745 microseconds. The threshold below is 50 microseconds — 250x above
    the honest reading and 15x below the bug.

    Repeats matter here: the probe reports a median per size, and a single
    preempted run inside a sub-microsecond window is not a finding. (Asserting on
    `max` across repeats flaked on exactly that.)"""
    target = Target("yours", _write(tmp_path, "constant", CONSTANT), "f")
    result = run_probe(target, _ints, sizes=[100, 400, 1600, 6400], repeats=5)
    times = [p.student.ms for p in result.points]
    assert all(t is not None for t in times), times
    assert max(times) < 0.05, times


def test_the_timed_call_runs_without_the_tracer(tmp_path):
    """The second call inside the harness is the timed one, and tracemalloc may
    not be running during it."""
    target = Target("yours", _write(tmp_path, "guard", TRACER_GUARD), "f")
    run = run_one(target, [[1, 2, 3]])
    assert run.ok, run.error


def test_every_call_gets_a_fresh_copy(tmp_path):
    """Without a copy per call the warm-up would leave the timed call a mutated
    argument, and the measurement would describe a different job."""
    target = Target("yours", _write(tmp_path, "inplace", INPLACE_GUARD), "f")
    run = run_one(target, [[3, 1, 2]])
    assert run.ok, run.error


# --------------------------------------------------- failure is data


def test_an_exception_at_scale_is_reported_with_its_size(tmp_path):
    """The whole point of the rewrite: the `top_k_frequent_elements` session
    raised on every probe input and dojo said nothing, then the AI reviewed the
    code as correct."""
    target = Target("yours", _write(tmp_path, "boom", RAISES_ABOVE), "f")
    result = run_probe(target, _ints, sizes=[100, 200, 400, 800], repeats=2)
    failure = result.first_failure()
    assert failure is not None
    assert failure.n == 400
    assert "ValueError" in failure.student.error
    assert "Not enough elements!" in failure.student.error


def test_the_ascent_stops_at_the_failure(tmp_path):
    """Sizes above a failure say nothing new, and cost real seconds."""
    target = Target("yours", _write(tmp_path, "boom", RAISES_ABOVE), "f")
    result = run_probe(target, _ints, sizes=[100, 200, 400, 800, 1600], repeats=1)
    assert [p.n for p in result.points] == [100, 200, 400]


def test_a_failure_is_not_retried(tmp_path):
    """A raising call is not a noisy measurement; repeating it wastes the budget."""
    target = Target("yours", _write(tmp_path, "boom", RAISES_ABOVE), "f")
    result = run_probe(target, _ints, sizes=[100, 400], repeats=5)
    assert result.points[-1].n == 400
    assert result.first_failure().student.error is not None


def test_a_timeout_is_reported_as_a_failure(tmp_path):
    target = Target("yours", _write(tmp_path, "slow", SLOW), "f")
    run = run_one(target, [[1, 2, 3]], timeout=1.0)
    assert not run.ok
    assert "timed out" in run.error


def test_an_import_error_is_reported_not_swallowed(tmp_path):
    target = Target("yours", _write(tmp_path, "broken", "this is not python"), "f")
    run = run_one(target, [[1]])
    assert not run.ok
    assert "import failed" in run.error


# ------------------------------------------------------- the pairing


def test_the_ratio_is_the_student_over_the_reference():
    """Pure property: the ratio is student/reference, per axis. Asserted on
    constructed runs rather than measured ones — a timing band here would be a
    test of the machine."""
    point = ScalePoint(
        n=100,
        student=Run(ms=3.0, peak=30, digest="same"),
        reference=Run(ms=1.5, peak=15, digest="same"),
    )
    assert point.time_ratio == 2.0
    assert point.space_ratio == 2.0
    assert point.outputs_agree is True
    assert point.time_ratio is not None and point.space_ratio is not None


def test_a_missing_or_failed_side_yields_no_ratio():
    student = Run(ms=3.0, peak=30)
    assert ScalePoint(n=100, student=student).time_ratio is None
    assert ScalePoint(n=100, student=student, reference=Run(error="boom")).time_ratio is None
    assert ScalePoint(n=100, student=Run(error="boom"), reference=Run(ms=1.0)).space_ratio is None


def test_the_probe_pairs_every_size(tmp_path):
    """End-to-end smoke: both targets run at every size and produce a usable
    ratio. No band is asserted — that is `growth`'s job, on synthetic series."""
    student = Target("yours", _write(tmp_path, "s", LINEAR), "f")
    reference = Target("reference", _write(tmp_path, "r", LINEAR), "f")
    result = run_probe(student, _ints, reference, sizes=[100, 200, 400, 800], repeats=2)
    assert [p.n for p in result.points] == [100, 200, 400, 800]
    ratios = [r for _, r in result.time_ratios]
    assert all(r is not None and r > 0 for r in ratios), ratios
    assert result.first_mismatch() is None


def test_a_mismatching_output_is_flagged(tmp_path):
    student = Target("yours", _write(tmp_path, "wrong", "def f(a):\n    return -1\n"), "f")
    reference = Target("reference", _write(tmp_path, "right", "def f(a):\n    return sum(a)\n"), "f")
    result = run_probe(student, _ints, reference, sizes=[100, 200], repeats=1)
    assert result.first_mismatch() is not None
    assert result.points[0].outputs_agree is False


def test_output_comparison_can_be_order_insensitive(tmp_path):
    """The same answer in a different order is not a failure — but only when the
    problem says so, which is what `compare` carries."""
    a = Target("yours", _write(tmp_path, "a", "def f(a):\n    return list(reversed(a))\n"), "f")
    b = Target("reference", _write(tmp_path, "b", "def f(a):\n    return list(a)\n"), "f")
    strict = run_probe(a, _ints, b, sizes=[100], repeats=1, compare="strict")
    assert strict.points[0].outputs_agree is False
    loose = run_probe(a, _ints, b, sizes=[100], repeats=1, compare="sorted")
    assert loose.points[0].outputs_agree is True


def test_without_a_reference_there_are_no_ratios(tmp_path):
    target = Target("yours", _write(tmp_path, "s", LINEAR), "f")
    result = run_probe(target, _ints, sizes=[100, 200], repeats=1)
    assert result.has_reference is False
    assert all(r is None for _, r in result.time_ratios)
    assert result.first_failure() is None  # it ran fine — just nothing to compare


def test_a_reference_failure_stops_the_ascent(tmp_path):
    """A reference that cannot run at a size cannot be compared there, and
    comparing beyond it would be comparing against nothing."""
    student = Target("yours", _write(tmp_path, "s", LINEAR), "f")
    reference = Target("reference", _write(tmp_path, "r", RAISES_ABOVE), "f")
    result = run_probe(student, _ints, reference, sizes=[100, 200, 400, 800], repeats=1)
    assert result.reference_failure().n == 400
    assert [p.n for p in result.points] == [100, 200, 400]


def test_ladder_ends_where_it_is_asked_to():
    assert ladder(6400) == [100, 200, 400, 800, 1600, 3200, 6400]
    assert ladder(400, points=3) == [100, 200, 400]


# ------------------------------------------- probe -> verdict, end to end


def test_end_to_end_verdict_matches_for_the_same_algorithm(tmp_path):
    """The same implementation on both sides is the cleanest possible control:
    any verdict other than 'matches' would be the measurement lying.

    Measured stability of this control on an idle machine: the ratio trend lands
    in 0.87-1.04 across repeated runs, against the 0.71-1.40 matching band — a
    ~5x margin. Five repeats buys headroom without pretending the number is
    exact."""
    student = Target("yours", _write(tmp_path, "s", LINEAR), "f")
    reference = Target("reference", _write(tmp_path, "r", LINEAR), "f")
    result = run_probe(student, _ints, reference, sizes=[100, 200, 400, 800, 1600, 3200], repeats=5)
    verdict = growth.verdict(result.time_ratios, declared_class="O(n)")
    assert verdict.kind == "matches", (verdict, result.time_ratios)


def test_end_to_end_a_failure_outranks_the_growth_verdict(tmp_path):
    """If the code breaks at scale, that is the finding — not the growth."""
    student = Target("yours", _write(tmp_path, "s", RAISES_ABOVE), "f")
    reference = Target("reference", _write(tmp_path, "r", LINEAR), "f")
    result = run_probe(student, _ints, reference, sizes=[100, 200, 400, 800], repeats=1)
    failure = result.first_failure()
    verdict = growth.verdict(
        result.time_ratios,
        declared_class="O(n)",
        failure=failure.student.error,
        failed_at=failure.n,
    )
    assert verdict.kind == "failed"
    assert "400" in verdict.note


# ------------------------------------------------- smallest failing input


def test_mismatch_is_localized_below_the_first_disagreeing_size(tmp_path):
    """A finding at n=6400 is hard to reason about; the same finding at n=25 is
    a counterexample. The walk down is bounded, so it cannot run away."""
    from dojo.profiler.probe import locate_mismatch

    # Agrees up to 200, disagrees above it — so the boundary is 400, and the
    # walk back down must find it rather than reporting the top of the ladder.
    student = Target(
        "yours",
        _write(tmp_path, "s", "def f(a):\n    return len(a) if len(a) <= 200 else -1\n"),
        "f",
    )
    reference = Target("reference", _write(tmp_path, "r", "def f(a):\n    return len(a)\n"), "f")
    assert locate_mismatch(student, reference, _ints, 1600) == 400


def test_localization_stops_when_the_two_agree_again(tmp_path):
    from dojo.profiler.probe import locate_mismatch

    student = Target("yours", _write(tmp_path, "s", "def f(a):\n    return len(a) + 1\n"), "f")
    reference = Target("reference", _write(tmp_path, "r", "def f(a):\n    return len(a)\n"), "f")
    # They disagree at every size, so the walk reaches the floor and reports the
    # smallest size it tested, never something below it.
    assert locate_mismatch(student, reference, _ints, 400, floor=50, steps=5) == 50


def test_a_decorated_reference_snippet_runs(tmp_path):
    """Curated references carry their own `@reference("slug")` line, and the
    decorator is resolved in the *snippet's* namespace — which is not the
    harness's. Injecting them there is what makes a real reference runnable."""
    source = textwrap.dedent(
        '''
        @reference("demo")
        def canonical(s: str) -> int:
            return len(s)
        '''
    )
    target = Target("reference", _write(tmp_path, "reference_demo", source), "canonical")
    run = run_one(target, ["abcd"])
    assert run.ok, run.error
    assert run.digest is not None  # it ran and produced a value


def test_a_reference_that_disagrees_on_output_is_detected(tmp_path):
    student = Target("yours", _write(tmp_path, "s", "def f(a):\n    return 1\n"), "f")
    reference = Target(
        "reference",
        _write(
            tmp_path,
            "r",
            textwrap.dedent(
                '''
                @reference("demo")
                def canonical(a):
                    return 2
                '''
            ),
        ),
        "canonical",
    )
    result = run_probe(student, _ints, reference, sizes=[100, 200], repeats=1)
    assert result.first_mismatch() is not None
