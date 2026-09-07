"""Curve fitting: the classifier must recognize the canonical shapes."""

import math

from dojo.profiler.fit import classify

SIZES = [50, 100, 200, 400, 800, 1600]


def _mk(fn, scale):
    return [fn(n) * scale for n in SIZES]


def test_classify_constant():
    result = classify(SIZES, _mk(lambda n: 1.0, 12.0))
    assert result.best_class == "O(1)"
    assert result.r2 > 0.99


def test_classify_linear():
    result = classify(SIZES, _mk(lambda n: n, 0.01))
    assert result.best_class == "O(n)"
    assert result.r2 > 0.99


def test_classify_quadratic():
    result = classify(SIZES, _mk(lambda n: n * n, 1e-6))
    assert result.best_class == "O(n^2)"
    assert result.r2 > 0.99


def test_classify_nlogn():
    result = classify(SIZES, _mk(lambda n: n * math.log(max(n, 2)), 0.01))
    assert result.best_class == "O(n log n)"
    assert result.r2 > 0.99


def test_classify_not_enough_points():
    result = classify([100], [1.0])
    assert result.best_class == "unknown"
    assert not result.confident


def test_classify_noisy_linear_is_not_confident():
    # A linear trend buried in noise: class may be wrong, but confidence flag off.
    result = classify(
        SIZES,
        [n * 0.01 + (i % 3) * 500 for i, n in enumerate(SIZES)],
    )
    assert not result.confident or result.r2 >= 0.9


def test_occam_prefers_simpler_class_when_ambiguous():
    # Real trap: 4 small sizes with constant overhead make O(n log n) out-fit
    # O(n) by a hair. The tiebreak must prefer the simpler class and say so.
    values = [1344.0, 1568.0, 2304.0, 3904.0]  # measured peak bytes, linear code
    result = classify([50, 100, 200, 400], values)
    assert result.best_class == "O(n)"
    assert not result.confident
    assert "ambiguous" in result.note
