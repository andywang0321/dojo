"""Curve fitting: canonical shapes are recognized, and the classifier never
claims a class the data cannot support.

Everything here is synthetic and deterministic — the decision rule is tested
against known shapes and known noise, not against wall-clock timing. That is
the point of the v0.11 rewrite: the old suite asserted a *measured* class and
flaked under load, which is a test of the machine, not of the rule.
"""

import math
import random

import pytest

from dojo.profiler.fit import classify

SIZES = [100, 200, 400, 800, 1600, 3200, 6400]

SHAPES = {
    "O(1)": lambda n: 1.0,
    "O(n)": lambda n: float(n),
    "O(n log n)": lambda n: n * math.log(max(n, 2)),
    "O(n^2)": lambda n: float(n * n),
    "O(n^3)": lambda n: float(n**3),
}


def _series(shape, noise=0.0, seed=0, overhead=0.2):
    """A measured-looking series: the shape, a constant overhead (every real
    measurement carries one), and multiplicative noise scaled with the value."""
    rng = random.Random(seed)
    fn = SHAPES[shape]
    scale = 1.0 / fn(SIZES[0])
    return [
        (overhead + scale * fn(n)) * (1 + rng.uniform(-noise, noise))
        for n in SIZES
    ]


@pytest.mark.parametrize("shape", list(SHAPES))
def test_clean_series_classify_exactly(shape):
    result = classify(SIZES, _series(shape))
    assert result.best_class == shape
    assert result.label == shape
    assert result.confident and result.bracket is None
    assert result.r2 > 0.99


def test_flat_series_is_constant_not_a_bracket():
    """Every candidate can fit a flat series with a zero coefficient, so the
    generic rule would bracket it with all of them. Flatness is evidence *for*
    constant cost."""
    result = classify(SIZES, [12.0] * len(SIZES))
    assert result.best_class == "O(1)"
    assert result.bracket is None
    assert "flat" in result.note


@pytest.mark.parametrize("shape", list(SHAPES))
@pytest.mark.parametrize("noise", [0.02, 0.05, 0.10, 0.20, 0.30])
def test_never_claims_a_class_the_noise_cannot_support(shape, noise):
    """The rule's falsifiable property: across a noise sweep the classifier
    either names the true class or *brackets* it. It must never return a
    single wrong class — a confidently wrong verdict is the failure this
    whole rewrite exists to remove."""
    wrong = []
    for seed in range(12):
        result = classify(SIZES, _series(shape, noise=noise, seed=seed), spread=noise)
        if result.best_class == shape:
            continue
        if result.bracket and shape in result.bracket:
            continue
        wrong.append((seed, result.best_class, result.bracket))
    assert not wrong, f"{shape} at {noise:.0%} noise produced {wrong}"


def test_coarse_classes_keep_their_detection_power():
    """Bracketing must not swallow the distinctions that *are* identifiable:
    a quadratic stays quadratic even under heavy noise."""
    result = classify(SIZES, _series("O(n^2)", noise=0.20, seed=3), spread=0.20)
    assert result.best_class == "O(n^2)"


def test_the_n_vs_nlogn_trap_brackets_instead_of_guessing():
    """The regression that started this: a genuine O(n log n) sort measured
    slope 1.005-1.030 across four trials, but the classifier's magic threshold
    was 1.06, so it reported O(n) — a confident wrong answer. Over this probe
    ladder the two shapes differ by ~0.3% of the signal variance, which is
    below realistic timing noise, so the honest output is the range."""
    sort_times = [0.007, 0.014, 0.028, 0.054, 0.109, 0.234, 0.497]
    result = classify(SIZES, sort_times, spread=0.06)
    assert result.bracket == ("O(n)", "O(n log n)")
    assert result.best_class == "O(n)"  # the conservative read
    assert not result.confident
    assert result.label == "O(n)…O(n log n)"
    assert "cannot separate" in result.note


def test_constant_overhead_does_not_force_a_wrong_single_class():
    # Real trap from v0.5: 4 small sizes with constant overhead make O(n log n)
    # out-fit O(n) by a hair on peak bytes.
    values = [1344.0, 1568.0, 2304.0, 3904.0]
    result = classify([50, 100, 200, 400], values)
    assert result.best_class == "O(n)"
    assert not result.confident
    assert result.bracket is not None or "suggestive" in result.note


def test_not_enough_points():
    result = classify([100], [1.0])
    assert result.best_class == "unknown"
    assert not result.confident


def test_values_below_timer_resolution_are_constant():
    result = classify(SIZES, [1e-4] * len(SIZES))
    assert result.best_class == "O(1)"
    assert "resolution" in result.note
