"""The judge: correctness evaluation against visible, generated, and
oracle-checked test cases.

Design: student code is executed in a subprocess with a JSON protocol —
import the workbench file, call the problem's function, compare results by
JSON equality (or a per-case comparator: sorted / rounded / approx /
predicate / ops). The subprocess isolates hangs (timeout) and crashes from
the session.

`ORACLES` are brute-force correctness anchors; `REFERENCES` (v0.12) are
canonical intended-complexity solutions used as the scale/performance baseline.
See registry.py for why they are separate.
"""

from dojo.judge.registry import (
    CHECKERS,
    JUDGE_CASES,
    ORACLES,
    PROFILER_INPUTS,
    REFERENCES,
)
from dojo.judge.runner import CaseResult, JudgeReport, run_cases


def reference_source(slug: str) -> str | None:
    """Source of the canonical reference for ``slug``, or None.

    The probe runs a reference in its own subprocess, so it needs the source
    rather than the object. The decorated source is returned as-is: the probe
    harness defines no-op registry decorators, so ``@reference("slug")`` executes
    harmlessly there."""
    import inspect

    fn = REFERENCES.get(slug)
    if fn is None:
        return None
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return None

__all__ = [
    "CHECKERS",
    "JUDGE_CASES",
    "ORACLES",
    "PROFILER_INPUTS",
    "REFERENCES",
    "CaseResult",
    "JudgeReport",
    "reference_source",
    "run_cases",
]
