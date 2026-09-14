"""The growth verdict: how a student's cost curve compares with a reference.

Pure logic on a paired ratio series — no clock, no subprocess. `probe.py`
produces the numbers; this module decides what they mean.

Every test here builds the ratio series that a *real* class pair would produce
(`student_class` against `reference_class` over the ladder), rather than an
abstract "trend" number. That is the point of the module: the ratio cancels the
constant factor and everything else the two solutions share, leaving only the
difference in growth, so a class pair is what the input actually means.

The counter-case is equally important: a cost curve that matches *no* class —
n^1.5 sits between n and n^2 — must come back unresolved. The v0.11 defect was
naming a class in exactly this situation.
"""

import math
import random
from statistics import median

import pytest

from dojo.profiler.growth import MATCH_TOLERANCE, verdict

LADDER = [100, 200, 400, 800, 1600, 3200, 6400]

#: The linear shape of each class, used to synthesise a ratio series.
SHAPES = {
    "O(1)": lambda n: 1.0,
    "O(log n)": lambda n: math.log(max(n, 2)),
    "O(n)": lambda n: float(n),
    "O(n log n)": lambda n: n * math.log(max(n, 2)),
    "O(n^2)": lambda n: float(n * n),
}


def ratio_series(student, reference, *, jitter=0.0, seed=1, ladder=LADDER, shape=None):
    """The student/reference cost ratio at each size — what a paired probe
    would report if both implementations were exactly these shapes."""
    rng = random.Random(seed)
    f = shape or SHAPES[student]
    g = SHAPES[reference]
    return [
        (n, (f(n) / g(n)) * (1 + rng.uniform(-jitter, jitter)))
        for n in ladder
    ]


def test_identical_shape_matches():
    result = verdict(ratio_series("O(n)", "O(n)"), declared_class="O(n)")
    assert result.kind == "matches"
    assert result.steps == 0
    assert result.student_class == "O(n)"
    assert result.trend == pytest.approx(1.0, abs=0.05)


def test_a_constant_factor_difference_still_matches():
    """A solution 3x slower at *every* size has the same complexity — which is
    exactly what the ratio is there to see through."""
    series = [(n, 3.0 * r) for n, r in ratio_series("O(n)", "O(n)")]
    assert verdict(series, declared_class="O(n)").kind == "matches"


def test_jitter_within_noise_still_matches():
    for seed in range(5):
        series = ratio_series("O(n)", "O(n)", jitter=0.15, seed=seed)
        assert verdict(series, declared_class="O(n)").kind == "matches", seed


def test_one_class_worse_is_detected():
    """A sort-based solution against an O(n) reference: the n log n signature."""
    result = verdict(ratio_series("O(n log n)", "O(n)"), declared_class="O(n)")
    assert result.kind == "worse"
    assert result.steps == 1
    assert result.student_class == "O(n log n)"
    assert "class faster" in result.note


def test_two_classes_worse_is_detected():
    result = verdict(ratio_series("O(n^2)", "O(n)"), declared_class="O(n)")
    assert result.kind == "worse"
    assert result.steps == 2
    assert result.student_class == "O(n^2)"
    assert "classes faster" in result.note


def test_better_than_the_reference_is_reported():
    """An O(n) solution measured against an O(n log n) reference grows slower."""
    result = verdict(ratio_series("O(n)", "O(n log n)"), declared_class="O(n log n)")
    assert result.kind == "better"
    assert result.steps == -1
    assert result.student_class == "O(n)"


def test_a_constant_reference_measures_the_student_directly():
    """With a flat reference there is nothing to cancel, so the trend *is* the
    student's own growth. Two ranks apart: constant → logarithmic → linear."""
    result = verdict(ratio_series("O(n)", "O(1)"), declared_class="O(1)")
    assert result.kind == "worse"
    assert result.steps == 2
    assert result.student_class == "O(n)"


def test_a_shape_between_classes_is_unresolved_not_a_guess():
    """n^1.5 sits between n and n^2 (and closest to n log n). Naming it would be
    a guess, and guessing is what made the old profiler useless."""
    result = verdict(
        ratio_series("O(n)", "O(n)", shape=lambda n: n**1.5),
        declared_class="O(n)",
    )
    assert result.kind == "unresolved"
    assert result.student_class is None
    assert result.trend is not None  # the number is still reported
    assert "no complexity class" in result.note


def test_split_tolerance_boundary_is_where_the_classes_meet():
    """A few percent of exponent excess is noise; a large excess is one class.
    The boundary is the geometric midpoint between the two expected trends."""
    mild = verdict(
        ratio_series("O(n)", "O(n)", shape=lambda n: n**1.03), declared_class="O(n)"
    )
    assert mild.kind == "matches"
    clear = verdict(
        ratio_series("O(n)", "O(n)", shape=lambda n: n**1.25), declared_class="O(n)"
    )
    assert clear.kind == "worse" and clear.steps == 1
    assert MATCH_TOLERANCE > 1.0


def test_without_a_declared_class_only_the_direction_is_claimed():
    """No anchor means no class name — report which way it grows and stop."""
    faster = verdict(ratio_series("O(n log n)", "O(n)"), declared_class=None)
    assert faster.kind == "worse"
    assert faster.student_class is None and faster.steps is None
    flat = verdict(ratio_series("O(n)", "O(n)"), declared_class=None)
    assert flat.kind == "matches"
    slower = verdict(ratio_series("O(n)", "O(n^2)"), declared_class=None)
    assert slower.kind == "better"


def test_too_few_paired_points_is_unresolved():
    """Failures truncate the ladder, so short series are normal, not exceptional."""
    assert verdict(ratio_series("O(n log n)", "O(n)")[:3], declared_class="O(n)").kind == "unresolved"
    assert verdict([], declared_class="O(n)").kind == "unresolved"


def test_unusable_ratios_are_skipped():
    series = [(100, None), (200, 0.0), (400, float("inf")), (800, 1.0), (1600, 1.0)]
    assert verdict(series, declared_class="O(n)").kind == "unresolved"


def test_a_smooth_ratio_is_not_understated():
    """Regression: the trend estimator and the expected trends must use the same
    windowing, or a genuine n log n signature reads as 'matches'."""
    result = verdict(ratio_series("O(n log n)", "O(n)"), declared_class="O(n)")
    assert result.trend == pytest.approx(1.7, abs=0.15)  # not 1.0, not 1.9
    assert result.steps == 1


def test_failed_reports_the_size_and_the_message():
    result = verdict(
        ratio_series("O(n)", "O(n)"),
        declared_class="O(n)",
        failure="ValueError: Not enough elements!",
        failed_at=400,
    )
    assert result.kind == "failed"
    assert "400" in result.note
    assert "ValueError" in result.note


def test_unreferenced_when_there_is_no_baseline():
    result = verdict([], declared_class="O(n)", has_reference=False)
    assert result.kind == "unreferenced"
    assert "reference" in result.note


def test_a_scale_failure_outranks_a_missing_reference():
    """The code broke at scale — that is a finding whether or not a reference
    exists to compare growth against. Reporting 'no reference' instead would bury
    the one thing the probe is uniquely able to see."""
    result = verdict(
        [],
        declared_class="O(n)",
        has_reference=False,
        failure="ValueError: Not enough elements!",
        failed_at=400,
    )
    assert result.kind == "failed"
    assert "400" in result.note
