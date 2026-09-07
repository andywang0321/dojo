"""The judge: correctness evaluation against visible, generated, and
oracle-checked test cases.

Design: student code is executed in a subprocess with a JSON protocol —
import the workbench file, call the problem's function, compare results by
JSON equality. The subprocess isolates hangs (timeout) and crashes from the
session.
"""

from dojo.judge.registry import JUDGE_CASES, ORACLES, PROFILER_INPUTS
from dojo.judge.runner import CaseResult, JudgeReport, run_cases

__all__ = [
    "JUDGE_CASES",
    "ORACLES",
    "PROFILER_INPUTS",
    "CaseResult",
    "JudgeReport",
    "run_cases",
]
