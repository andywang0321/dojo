"""Empirical complexity fitting.

Honesty contract: this *classifies evidence*, it does not prove asymptotic
bounds, and it must never emit a class the data cannot support.

The rule (v0.11). Each candidate class f is fitted to the measurements as
``y = k·f(n) + c`` by least squares, and the candidates whose residual stays
within the measurement's own noise of the best residual are all considered
*plausible*. The report is the simplest plausible class, plus a bracket
naming the classes the data cannot tell apart.

This replaces an R²-comparison plus a magic log-log slope threshold
(``NLN_SLOPE_THRESHOLD = 1.06``). That threshold sat *above* the slope
actually measured for a genuine O(n log n) function (1.005-1.030 over four
trials, biased low by the additive overhead every measurement carries), so
sort-based solutions were classified O(n) every time, while tracemalloc
contamination pushed allocation-heavy linear code the other way. Two errors
cancelling made the output look plausible.

The deeper reason a threshold cannot work: over the probe ladder the O(n) and
O(n log n) shapes differ by only ~0.3% of the signal variance, which is well
below realistic timing noise. They are not separable by fit quality at that
noise, and the honest output is a bracket — not a guess. Coarser distinctions
(n vs n², n² vs n³) separate by orders of magnitude and are still reported as
single classes with confidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_CANDIDATES: dict[str, callable] = {
    "O(1)": lambda n: 1.0,
    "O(n)": lambda n: float(n),
    "O(n log n)": lambda n: n * math.log(max(n, 2)),
    "O(n^2)": lambda n: n * n,
    "O(n^3)": lambda n: n**3,
}

#: Complexity order — the first *plausible* candidate is the conservative read.
_ORDER = ("O(1)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)")

MIN_POINTS = 3
MIN_R2 = 0.9

#: Noise the repeats cannot see: cache, allocator and branch-predictor effects
#: move the constant factor in ways that are systematic rather than random, so
#: a model has to beat its rivals by more than this share of the signal before
#: it is claimed on its own. Every real measurement also supplies its own
#: repeat spread, which usually dominates this floor.
SYSTEMATIC_NOISE = 0.03

#: How many noise-widths of improvement a rival must show to be ruled out.
NOISE_MARGIN = 2.0


@dataclass
class FitResult:
    best_class: str
    #: The classes the data cannot separate, simplest first; None when the
    #: winner is decisive. Populated results are never `confident`.
    bracket: tuple[str, ...] | None
    r2: float
    loglog_slope: float | None
    confident: bool
    note: str

    @property
    def label(self) -> str:
        """What to show the student: one class, or the range that is all the
        measurement supports."""
        if self.bracket and len(self.bracket) > 1:
            return f"{self.bracket[0]}…{self.bracket[-1]}"
        return self.best_class


def _ols_rss(xs: list[float], ys: list[float]) -> float:
    """Residual sum of squares of the least-squares fit y = k·x + c.

    A constant regressor (the O(1) candidate) makes the design matrix
    degenerate; there the best fit is the mean, which is the same formula
    with k = 0."""
    n = len(xs)
    if n == 0:
        return float("inf")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return sum((y - mean_y) ** 2 for y in ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sxx
    intercept = mean_y - slope * mean_x
    return sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))


def _loglog_slope(sizes: list[float], values: list[float]) -> float | None:
    """Diagnostic only — no longer the decision rule (see the module docstring)."""
    points = [
        (math.log10(n), math.log10(v))
        for n, v in zip(sizes, values)
        if n > 0 and v > 0
    ]
    if len(points) < MIN_POINTS:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom


def _noise_floor(values: list[float], spread: float | None) -> float:
    """The residual a model may leave and still count as "fits fine".

    Noise is multiplicative (timing error scales with the value), so the floor
    scales with the sum of squares. ``spread`` is the observed relative
    half-range across repeats; its variance is spread²/3 (uniform)."""
    frac = max(spread or 0.0, SYSTEMATIC_NOISE)
    return frac**2 / 3.0 * sum(v * v for v in values)


def staircase_safe_points(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Anti-alias a measurement series before fitting (v0.8.1).

    Peak space for container-heavy solutions is a power-of-two staircase:
    a set/dict table serves the same capacity across a 2-4x range of n,
    then jumps. Sampled at exact doublings, consecutive points land in
    pairs on the same step, and a linear structure aliases as exponent 2 —
    the reported contains_duplicate "O(n^2)" space flag. Taking every
    second point quadruples the sample spacing: in both CPython growth
    regimes (x4 for small tables, x2 for large ones) a whole number of
    steps is crossed per sample, so linear growth reads as slope 1. Smooth
    O(n) and genuine O(n^2) data are unaffected — slopes 1 and 2 both
    survive a spacing change.

    This is a measurement fix, not a verdict shortcut: it removes a known
    systematic artifact from the points the classifier sees; R² and the
    honesty flags still come from the data.
    """
    if (len(points) + 1) // 2 < MIN_POINTS:
        return points  # subsampling would starve the fit; keep the raw data
    return points[::2]


def classify(
    sizes: list[int], values: list[float], spread: float | None = None
) -> FitResult:
    """Fit measured values across sizes to candidate growth classes.

    ``spread`` is the measurement's own relative repeat spread; it sets how
    much residual difference counts as noise rather than signal."""
    points = [(n, v) for n, v in zip(sizes, values) if n > 0 and v is not None]
    if len(points) < MIN_POINTS:
        return FitResult(
            best_class="unknown",
            bracket=None,
            r2=0.0,
            loglog_slope=None,
            confident=False,
            note=f"not enough data points ({len(points)} < {MIN_POINTS})",
        )
    ns = [float(p[0]) for p in points]
    vs = [float(p[1]) for p in points]

    if max(vs) <= 1e-3:
        return FitResult(
            best_class="O(1)",
            bracket=None,
            r2=1.0,
            loglog_slope=None,
            confident=False,
            note="values below timing resolution; treated as constant",
        )

    slope = _loglog_slope(ns, vs)
    rss = {name: _ols_rss([f(n) for n in ns], vs) for name, f in _CANDIDATES.items()}
    best_rss = min(rss.values())
    floor = _noise_floor(vs, spread)

    mean = sum(vs) / len(vs)
    syy = sum((v - mean) ** 2 for v in vs)

    # A flat series is evidence *for* constant cost, not ambiguity: every
    # candidate can fit it by taking a zero coefficient, so the generic rule
    # below would bracket it with all of them.
    if rss["O(1)"] <= NOISE_MARGIN * floor:
        return FitResult(
            best_class="O(1)",
            bracket=None,
            r2=1.0,
            loglog_slope=slope,
            confident=True,
            note="flat within measurement noise — no growth to classify",
        )

    # Everything that fits within the noise of the best residual stays on the
    # table; the simplest of those is the conservative read.
    plausible = tuple(name for name in _ORDER if rss[name] <= best_rss + NOISE_MARGIN * floor)
    chosen = plausible[0]

    r2 = 1.0 - rss[chosen] / syy if syy else 1.0

    if len(plausible) > 1:
        noise = f" (repeat spread {spread:.1%})" if spread else ""
        return FitResult(
            best_class=chosen,
            bracket=plausible,
            r2=round(r2, 4),
            loglog_slope=slope,
            confident=False,
            note=f"cannot separate {' from '.join(plausible)} at this noise level{noise}",
        )
    if r2 < MIN_R2:
        return FitResult(
            best_class=chosen,
            bracket=None,
            r2=round(r2, 4),
            loglog_slope=slope,
            confident=False,
            note="no candidate fits well (R² < 0.9); treat class as suggestive",
        )
    return FitResult(
        best_class=chosen,
        bracket=None,
        r2=round(r2, 4),
        loglog_slope=slope,
        confident=True,
        note="",
    )
