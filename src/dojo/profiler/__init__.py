"""The scale probe: measure a solution against a reference, at increasing size.

`probe` runs both implementations at a ladder of sizes in isolated subprocesses
and reports, per size, the wall time, peak memory, the result digest, and any
exception or timeout. `growth` turns the paired ratios into a verdict.

There is deliberately no absolute complexity fitting here any more (v0.12).
Fitting a single curve to wall-clock samples cannot separate O(n) from
O(n log n) — they differ by ~0.3% of the signal variance over a feasible ladder
while the noise is 3-12% — and the honest output of trying was a bracket nobody
could use. Measuring the student *against a reference implementation* cancels
every constant factor the two share, which is what makes a verdict possible.
"""

from dojo.profiler.growth import (
    BETTER,
    FAILED,
    MATCHES,
    UNREFERENCED,
    UNRESOLVED,
    WORSE,
    Verdict,
    verdict,
)
from dojo.profiler.probe import (
    DEFAULT_MAX_N,
    DEFAULT_REPEATS,
    DEFAULT_TIMEOUT,
    LADDER_POINTS,
    Probe,
    Run,
    ScalePoint,
    Target,
    ladder,
    locate_mismatch,
    run_one,
    run_probe,
)

__all__ = [
    "BETTER",
    "DEFAULT_MAX_N",
    "DEFAULT_REPEATS",
    "DEFAULT_TIMEOUT",
    "FAILED",
    "LADDER_POINTS",
    "MATCHES",
    "Probe",
    "Run",
    "ScalePoint",
    "Target",
    "UNREFERENCED",
    "UNRESOLVED",
    "WORSE",
    "Verdict",
    "ladder",
    "locate_mismatch",
    "run_one",
    "run_probe",
    "verdict",
]
