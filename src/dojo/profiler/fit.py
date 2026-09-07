"""Empirical complexity fitting.

Honesty contract: this *classifies evidence*, it does not prove asymptotic
bounds. We fit candidate growth curves by least squares and report the best
R², plus the log-log slope, so "O(n) at tested scales" and "noisy data" are
distinguishable. A mismatch against the problem's expected class is a signal
to investigate — possibly a real algorithmic problem, possibly a measurement
artifact.
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

MIN_POINTS = 3
MIN_R2 = 0.9
#: When two growth classes fit almost equally well (R² within EPS), prefer
#: the simpler one — claiming O(n) when the evidence is ambiguous between
#: O(n) and O(n log n) is the defensible, conservative read.
AMBIGUITY_EPS = 0.01

#: The one ambiguity the simpler-is-better rule can't resolve: O(n) vs
#: O(n log n) on a narrow size range. Their log-log slope differs — pure
#: O(n) sits at ~1.0 (below with constant overhead), while O(n log n) sits
#: at 1 + 1/ln(n) ≈ 1.1-1.2 at the sizes we probe.
NLN_SLOPE_THRESHOLD = 1.06

_COMPLEXITY_RANK = {"O(1)": 0, "O(n)": 1, "O(n log n)": 2, "O(n^2)": 3, "O(n^3)": 4}


@dataclass
class FitResult:
    best_class: str
    r2: float
    loglog_slope: float | None
    confident: bool
    note: str


def _ols_r2(xs: list[float], ys: list[float]) -> float:
    """R² of y ~ a·x + b by ordinary least squares."""
    n = len(xs)
    if n == 0:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    syy = sum((y - mean_y) ** 2 for y in ys)
    if syy == 0:
        return 1.0
    if sxx == 0:
        return 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    return max(0.0, 1.0 - ss_res / syy)


def _loglog_slope(sizes: list[int], values: list[float]) -> float | None:
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


def classify(sizes: list[int], values: list[float]) -> FitResult:
    """Fit measured values across sizes to candidate growth classes."""
    points = [(n, v) for n, v in zip(sizes, values) if n > 0 and v is not None]
    if len(points) < MIN_POINTS:
        return FitResult(
            best_class="unknown",
            r2=0.0,
            loglog_slope=None,
            confident=False,
            note=f"not enough data points ({len(points)} < {MIN_POINTS})",
        )
    ns = [p[0] for p in points]
    vs = [p[1] for p in points]

    if max(vs) <= 1e-3:
        return FitResult(
            best_class="O(1)",
            r2=1.0,
            loglog_slope=None,
            confident=False,
            note="values below timing resolution; treated as constant",
        )

    slope = _loglog_slope(ns, vs)

    scored = []
    for name, f in _CANDIDATES.items():
        xs = [f(n) for n in ns]
        scored.append((name, _ols_r2(xs, vs)))
    scored.sort(key=lambda pair: (-pair[1], _COMPLEXITY_RANK[pair[0]]))
    best_name, best_r2 = scored[0]

    # Occam: if a simpler class fits within AMBIGUITY_EPS of the best R²,
    # prefer it and flag the ambiguity instead of over-claiming.
    contenders = [
        (name, r2) for name, r2 in scored if best_r2 - r2 <= AMBIGUITY_EPS
    ]
    if len(contenders) > 1:
        names = {name for name, _ in contenders}
        if names == {"O(n)", "O(n log n)"} and slope is not None:
            chosen_name = "O(n log n)" if slope >= NLN_SLOPE_THRESHOLD else "O(n)"
        else:
            chosen_name = min(contenders, key=lambda pair: _COMPLEXITY_RANK[pair[0]])[0]
        chosen_r2 = next(r2 for name, r2 in contenders if name == chosen_name)
        return FitResult(
            best_class=chosen_name,
            r2=round(chosen_r2, 4),
            loglog_slope=slope,
            confident=False,
            note="ambiguous between "
            + " and ".join(sorted(names))
            + "; larger inputs would disambiguate",
        )

    if best_r2 < MIN_R2:
        return FitResult(
            best_class=best_name,
            r2=best_r2,
            loglog_slope=slope,
            confident=False,
            note="no candidate fits well (R² < 0.9); treat class as suggestive",
        )
    return FitResult(
        best_class=best_name,
        r2=best_r2,
        loglog_slope=slope,
        confident=True,
        note="",
    )
