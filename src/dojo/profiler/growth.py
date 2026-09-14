"""The growth verdict: how a student's cost curve compares with a reference.

Pure logic on a paired ratio series — no clock, no subprocess. `probe.py`
produces the numbers; this module decides what they mean.

The idea that makes this work: a ratio **cancels** everything the two solutions
have in common — interpreter overhead, the constant factor, cache behaviour,
allocator staircases. What is left is the difference in growth, and over the
default ladder that is ~1.9x for one class (n vs n log n) and ~64x for two
(n vs n^2), against a paired-measurement noise of a few percent. That is why
this is usable where the v0.11 absolute fit was not: the fit had to separate
shapes buried under a constant-factor ambiguity, and this never sees the
constant factor at all.

Classes survive only to **name** an observed ratio. The expected trend for a
candidate class ``f`` against the declared class ``g`` is
``(f(N)/f(n0)) / (g(N)/g(n0))``; the observed trend is matched to the nearest of
those in log space. Nothing is least-squares fitted, no R² is produced, and a
trend that sits between two classes is reported as unresolved rather than
rounded to one of them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

#: Complexity order — used to count how many classes apart two are.
ORDER = ("O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)", "O(2^n)")

#: log of each class's shape, so ratios can be compared without overflow
#: (2^n in linear space is not representable over a ladder like 100..6400).
_LOG_SHAPES = {
    "O(1)": lambda n: 0.0,
    "O(log n)": lambda n: math.log(math.log(max(n, 3))),
    "O(n)": lambda n: math.log(n),
    "O(n log n)": lambda n: math.log(n) + math.log(math.log(max(n, 3))),
    "O(n^2)": lambda n: 2 * math.log(n),
    "O(n^3)": lambda n: 3 * math.log(n),
    "O(2^n)": lambda n: n * math.log(2),
}

#: How far (as a ratio) the observed trend may sit from a class's expected trend
#: and still be called that class. 1.4 is the geometric midpoint between "same"
#: and "one class worse" on the default ladder, so the tolerance *is* the
#: decision boundary rather than a separate magic number.
MATCH_TOLERANCE = 1.4

#: Sizes per end of the trend window. Averaging the ends instead of reading the
#: endpoints is what keeps a single noisy point from deciding the verdict.
WINDOW = 2

MATCHES = "matches"
WORSE = "worse"
BETTER = "better"
UNRESOLVED = "unresolved"
FAILED = "failed"
UNREFERENCED = "unreferenced"


@dataclass
class Verdict:
    kind: str
    #: End-to-end ratio trend: how much the student/reference cost ratio moved
    #: across the ladder. 1.0 means "same growth".
    trend: float | None
    #: The class the trend names, relative to the declared one. None when the
    #: data does not support naming one.
    student_class: str | None
    reference_class: str | None
    #: Signed class steps against the reference (None when unanchored).
    steps: int | None
    note: str

    @property
    def resolved(self) -> bool:
        return self.kind in (MATCHES, WORSE, BETTER)

    @property
    def trend_label(self) -> str:
        """The cost-ratio movement to show beside the verdict: the one number
        that is always available, even when no class can be named."""
        if self.trend is None:
            return "—"
        return f"{self.trend:.2f}×"

    @property
    def label(self) -> str:
        """What the student sees in the table's measured column."""
        if self.kind == MATCHES:
            return self.student_class or "like the reference"
        if self.kind in (WORSE, BETTER) and self.student_class:
            return self.student_class
        if self.kind == FAILED:
            return "failed at scale"
        if self.kind == UNREFERENCED:
            return "no reference"
        return "unresolved"


def _clean(points: list[tuple[int, float | None]]) -> list[tuple[int, float]]:
    out = []
    for n, ratio in points:
        if n and n > 0 and ratio is not None and math.isfinite(ratio) and ratio > 0:
            out.append((n, math.log(ratio)))
    return out


def _windowed_log_trend(series: list[tuple[int, float]]) -> float | None:
    """Median of the last window minus median of the first, in log space.

    Both the observed series and each class's *expected* series go through this
    same estimator. That matters: a smooth ratio grows within the window too, so
    comparing an end-to-end factor against a windowed measurement would bias
    every verdict toward "matches"."""
    if len(series) < 2 * WINDOW:
        return None
    first = median(v for _, v in series[:WINDOW])
    last = median(v for _, v in series[-WINDOW:])
    return last - first


def _expected_log_trend(candidate: str, declared: str, sizes: list[int]) -> float:
    """The trend this estimator would report for an ideal candidate/declared
    pair measured over ``sizes``."""
    ref = _LOG_SHAPES[declared]
    shape = _LOG_SHAPES[candidate]
    series = [(n, shape(n) - ref(n)) for n in sizes]
    return _windowed_log_trend(series)


def _nearest_class(
    observed_log: float, declared: str, sizes: list[int]
) -> str | None:
    """The class whose expected trend is closest to the observed one, or None
    when none is close enough to claim."""
    best, best_gap = None, None
    for candidate in ORDER:
        gap = abs(_expected_log_trend(candidate, declared, sizes) - observed_log)
        if best_gap is None or gap < best_gap:
            best, best_gap = candidate, gap
    if best_gap is not None and best_gap <= math.log(MATCH_TOLERANCE):
        return best
    return None


def verdict(
    points: list[tuple[int, float | None]],
    *,
    declared_class: str | None = None,
    has_reference: bool = True,
    failure: str | None = None,
    failed_at: int | None = None,
) -> Verdict:
    """Turn a paired ratio series into a verdict.

    ``points`` are (n, student_ms/reference_ms) pairs; ``declared_class`` is the
    problem's target complexity, which anchors the comparison.
    """
    # A failure at scale is a finding in its own right: the code broke, and that
    # is true whether or not there is a reference to compare growth against.
    # Checking the baseline first would bury it.
    if failure is not None:
        where = f" at n={failed_at}" if failed_at else ""
        return Verdict(
            kind=FAILED,
            trend=None,
            student_class=None,
            reference_class=declared_class,
            steps=None,
            note=f"your code failed{where}: {failure}",
        )

    if not has_reference:
        return Verdict(
            kind=UNREFERENCED,
            trend=None,
            student_class=None,
            reference_class=None,
            steps=None,
            note=(
                "no reference solution is registered for this problem, so there "
                "is nothing to compare the growth against"
            ),
        )

    clean = _clean(points)
    log_trend = _windowed_log_trend(clean)
    trend = math.exp(log_trend) if log_trend is not None else None

    if log_trend is None:
        return Verdict(
            kind=UNRESOLVED,
            trend=None,
            student_class=None,
            reference_class=declared_class,
            steps=None,
            note=(
                "not enough paired measurements to compare growth "
                f"({len(clean)} usable points, need {2 * WINDOW})"
            ),
        )

    shown = f"grown {trend:.2f}x relative to the reference across the ladder"

    if declared_class not in _LOG_SHAPES:
        # No anchor: report the direction, never a class.
        if abs(log_trend) <= math.log(MATCH_TOLERANCE):
            return Verdict(MATCHES, trend, None, declared_class, None,
                           f"grows like the reference (cost ratio {shown})")
        kind = WORSE if trend > 1 else BETTER
        return Verdict(kind, trend, None, declared_class, None,
                       f"growth is {'faster' if trend > 1 else 'slower'} than the "
                       f"reference (cost ratio {shown})")

    sizes = [n for n, _ in clean]
    named = _nearest_class(log_trend, declared_class, sizes)
    if named is None:
        return Verdict(
            kind=UNRESOLVED,
            trend=trend,
            student_class=None,
            reference_class=declared_class,
            steps=None,
            note=(
                f"the cost ratio {shown} matches no complexity class closely "
                "enough to name — treat it as suggestive"
            ),
        )

    steps = ORDER.index(named) - ORDER.index(declared_class)
    if steps == 0:
        return Verdict(
            kind=MATCHES, trend=trend, student_class=named,
            reference_class=declared_class, steps=0,
            note=f"grows like the reference — consistent with {named}",
        )
    direction = "faster" if steps > 0 else "slower"
    word = "class" if abs(steps) == 1 else "classes"
    return Verdict(
        kind=WORSE if steps > 0 else BETTER,
        trend=trend,
        student_class=named,
        reference_class=declared_class,
        steps=steps,
        note=(
            f"grows {abs(steps)} {word} {direction} than the reference "
            f"({declared_class}) — {shown}"
        ),
    )
