"""Subprocess-isolated execution of student code against test cases."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HARNESS = r'''
import importlib.util
import json
import sys
import time


def main():
    function_name = sys.argv[1]
    with open("cases.json") as f:
        cases = json.load(f)
    spec = importlib.util.spec_from_file_location("solution", "solution.py")
    solution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(solution)
    fn = getattr(solution, function_name)
    results = []
    for i, case in enumerate(cases):
        label = case.get("label", f"case {i}")
        expected = case["expected"]
        t0 = time.perf_counter()
        try:
            got = fn(*case["args"])
            elapsed_ms = (time.perf_counter() - t0) * 1000
            passed = json.dumps(got, sort_keys=True, default=str) == json.dumps(
                expected, sort_keys=True, default=str
            )
            results.append(
                {
                    "label": label,
                    "passed": passed,
                    "expected": expected,
                    "got": got,
                    "error": None,
                    "elapsed_ms": elapsed_ms,
                }
            )
        except Exception as exc:  # noqa: BLE001 - the harness must survive anything
            results.append(
                {
                    "label": label,
                    "passed": False,
                    "expected": expected,
                    "got": None,
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_ms": (time.perf_counter() - t0) * 1000,
                }
            )
    print(json.dumps(results))


if __name__ == "__main__":
    main()
'''


@dataclass
class CaseResult:
    label: str
    passed: bool
    expected: Any
    got: Any
    error: str | None
    elapsed_ms: float


@dataclass
class JudgeReport:
    status: str  # correct | wrong_answer | error | timed_out
    results: list[CaseResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0

    @property
    def all_passed(self) -> bool:
        return self.status == "correct"


def run_cases(
    code_path: Path,
    function_name: str,
    cases: list[dict],
    timeout: float = 10.0,
) -> JudgeReport:
    """Run ``cases`` against the code in ``code_path`` in a subprocess."""
    if not cases:
        return JudgeReport(status="correct", total=0, passed=0)
    with tempfile.TemporaryDirectory(prefix="dojo_judge_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "solution.py").write_text(code_path.read_text())
        (tmp_path / "cases.json").write_text(json.dumps(cases))
        (tmp_path / "harness.py").write_text(HARNESS)
        try:
            proc = subprocess.run(
                [sys.executable, "harness.py", function_name],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return JudgeReport(status="timed_out", total=len(cases), passed=0)
        if proc.returncode != 0 or not proc.stdout.strip():
            return JudgeReport(
                status="error",
                total=len(cases),
                passed=0,
                results=[
                    CaseResult(
                        label="harness",
                        passed=False,
                        expected=None,
                        got=None,
                        error=(proc.stderr or "harness produced no output").strip()[:500],
                        elapsed_ms=0.0,
                    )
                ],
            )
        raw = json.loads(proc.stdout)
        results = [
            CaseResult(
                label=r["label"],
                passed=r["passed"],
                expected=r["expected"],
                got=r["got"],
                error=r["error"],
                elapsed_ms=r["elapsed_ms"],
            )
            for r in raw
        ]
        n_passed = sum(1 for r in results if r.passed)
        status = "correct" if n_passed == len(results) else "wrong_answer"
        return JudgeReport(
            status=status,
            results=results,
            total=len(results),
            passed=n_passed,
        )
