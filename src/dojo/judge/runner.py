"""Subprocess-isolated execution of student code against test cases.

Verdict model: case dicts carry an optional ``compare`` mode; the default is
strict JSON equality (no leniency — a non-serializable return fails the
case). Extra modes, per case:

- ``"sorted"``    — deep-sort both sides before JSON equality (any order).
- ``"rounded:n"`` — round floats to n decimals before equality.
- ``"approx:t"``  — recursive absolute tolerance t for floats.
- ``"predicate"`` — case key names a checker in ``judge/registry.CHECKERS``
  that receives (module, got, args) and returns a boolean (round-trip
  tests, property checks like "any valid sample").
- ``"ops"``       — class problems: case has ``ops`` (a list of
  [method, *args]) and ``expected`` (per-op outputs); the harness
  instantiates ``function_name`` and replays the sequence.
"""

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
import io
import json
import sys
import time

# Verdict semantics live in one place, shared with the curator's reference gate
# (v0.12) — the harness judges the student's code by the same rules the gate
# judges a canonical solution by.
from dojo.judge.compare import canonical, check_equal, rounded

try:
    from dojo.judge.registry import CHECKERS
except ImportError:  # pragma: no cover - dojo is always importable here
    CHECKERS = {}

PRINT_CAP = 4000


def isolated(call):
    """Run user code with its stdout captured: the protocol channel
    (stdout JSON) must never be polluted by prints (a real crash: a
    `print` in the solution corrupted the result JSON). The captured
    output rides along in the result so `dojo check` can show it."""
    real = sys.stdout
    buffer = io.StringIO()
    sys.stdout = buffer
    try:
        return call(), buffer.getvalue()[:PRINT_CAP]
    finally:
        sys.stdout = real


def main():
    function_name = sys.argv[1]
    with open("cases.json") as f:
        cases = json.load(f)
    spec = importlib.util.spec_from_file_location("solution", "solution.py")
    solution = importlib.util.module_from_spec(spec)
    isolated(lambda: spec.loader.exec_module(solution))
    results = []
    for i, case in enumerate(cases):
        label = case.get("label", f"case {i}")
        mode = case.get("compare", "strict")
        expected = case["expected"]
        t0 = time.perf_counter()
        try:
            printed = ""
            if "ops" in case:
                obj, ctor_out = isolated(
                    lambda: getattr(solution, function_name)(*case.get("ctor_args", []))
                )
                got, ops_out = isolated(
                    lambda: [getattr(obj, method)(*args) for method, *args in case["ops"]]
                )
                printed = (ctor_out + ops_out)[:PRINT_CAP]
            else:
                fn = getattr(solution, function_name)
                got, printed = isolated(lambda: fn(*case["args"]))
            if case.get("predicate"):
                passed, pred_out = isolated(
                    lambda: CHECKERS[case["predicate"]](solution, got, case["args"])
                )
                printed = (printed + pred_out)[:PRINT_CAP]
            else:
                passed = check_equal(got, expected, mode)
            results.append(
                {
                    "label": label,
                    "passed": passed,
                    "expected": expected,
                    "got": got,
                    "error": None,
                    "printed": printed,
                    "elapsed_ms": (time.perf_counter() - t0) * 1000,
                }
            )
        except BaseException as exc:  # noqa: BLE001 - SystemExit and friends included
            results.append(
                {
                    "label": label,
                    "passed": False,
                    "expected": expected,
                    "got": None,
                    "error": f"{type(exc).__name__}: {exc}",
                    "printed": "",
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
    printed: str = ""


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
                printed=r.get("printed", ""),
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
