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

Hardening (v0.13) — the parent can no longer be crashed or exhausted by the
child: output is collected through temp files and read back capped, the child
runs in its own process group and is killed as a group on timeout, the result
JSON is read as "the last parseable line" (so a print from a stray thread cannot
corrupt it), and a malformed protocol is a ``status="error"`` report rather than
an exception out of :func:`run_cases`.

``python=`` is the runner seam: the judge executes the harness with an
interpreter the *curriculum* chooses (v0.14 gives JAX its own venv, and a
non-Python curriculum supplies a different harness entirely).
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dojo.proc import apply_child_limits, last_json_object, run_capped

HARNESS = r'''
import importlib.util
import io
import json
import os
import sys
import tempfile
import time

# Verdict semantics live in one place, shared with the curator's reference gate
# (v0.12) — the harness judges the student's code by the same rules the gate
# judges a canonical solution by.
from dojo.judge.compare import canonical, check_equal, rounded

try:
    from dojo.judge.registry import CHECKERS
except ImportError:  # pragma: no cover - dojo is always importable here
    CHECKERS = {}

from dojo.proc import apply_child_limits

apply_child_limits()

PRINT_CAP = 4000
#: Raw file-descriptor 1 output kept per case (before the combined truncation).
FD_CAP = 8192


class Capped:
    """stdout replacement that stops growing at ``cap`` bytes.

    The old version accumulated everything in a StringIO and sliced afterwards,
    so the cap bounded what was *shown* and nothing else: a print loop reached
    ~1.9 GB in three seconds."""

    def __init__(self, cap=PRINT_CAP):
        self.cap = cap
        self._parts = []
        self._size = 0
        self.truncated = False

    def write(self, text):
        if self._size >= self.cap:
            self.truncated = True
            return len(text)
        room = self.cap - self._size
        self._parts.append(text[:room])
        self._size += min(len(text), room)
        if len(text) > room:
            self.truncated = True
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False

    def getvalue(self):
        text = "".join(self._parts)
        return text + "\n[dojo: further output truncated]" if self.truncated else text


#: The output of the most recent isolated call. Kept outside the call so a case
#: that *raises* still reports what it printed — prints are the debugging loop,
#: and they used to be discarded exactly when they were needed.
LAST = {"printed": ""}


def isolated(call):
    """Run user code with stdout captured at both levels.

    ``sys.stdout`` catches `print`; file descriptor 1 catches `os.write(1, …)`,
    `print(..., file=sys.__stdout__)`, and output a child process inherits. The
    fd goes to a temp file, and only a bounded slice is read back."""
    real_stdout = sys.stdout
    buffer = Capped()
    sys.stdout = buffer
    saved_fd = None
    tmp = None
    LAST["printed"] = ""
    try:
        try:
            sys.stdout.flush()
            saved_fd = os.dup(1)
            tmp = tempfile.TemporaryFile()
            os.dup2(tmp.fileno(), 1)
        except OSError:
            saved_fd = None
        try:
            return call()
        finally:
            LAST["printed"] = _collect(buffer, tmp)
    finally:
        sys.stdout = real_stdout
        if tmp is not None:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            if saved_fd is not None:
                try:
                    os.dup2(saved_fd, 1)
                    os.close(saved_fd)
                except OSError:
                    pass
            try:
                tmp.close()
            except OSError:
                pass


def _collect(buffer, tmp):
    text = buffer.getvalue()
    if tmp is not None:
        try:
            tmp.seek(0)
            raw = tmp.read(FD_CAP).decode("utf-8", "replace")
        except OSError:
            raw = ""
        if raw:
            text = text + ("\n" if text and not text.endswith("\n") else "") + raw
    return text[: 2 * PRINT_CAP]


def _expected(case):
    """The case's expected value — read defensively.

    It used to be read outside the per-case try, so one malformed case killed
    the harness and took every other case's result with it."""
    return case["expected"]


def main():
    function_name = sys.argv[1]
    with open("cases.json") as f:
        cases = json.load(f)
    spec = importlib.util.spec_from_file_location("solution", "solution.py")
    solution = importlib.util.module_from_spec(spec)
    try:
        isolated(lambda: spec.loader.exec_module(solution))
    except BaseException as exc:  # noqa: BLE001 - import failure is a real verdict
        results = [
            {
                "label": "import",
                "passed": False,
                "expected": None,
                "got": None,
                "error": f"{type(exc).__name__}: {exc}",
                "printed": LAST["printed"],
                "elapsed_ms": 0.0,
            }
        ]
        _emit(results)
        return
    results = []
    for i, case in enumerate(cases):
        label = case.get("label", f"case {i}")
        mode = case.get("compare", "strict")
        t0 = time.perf_counter()
        expected = None
        printed = ""
        try:
            expected = _expected(case)
            if "ops" in case:
                obj = isolated(
                    lambda: getattr(solution, function_name)(*case.get("ctor_args", []))
                )
                got = isolated(
                    lambda: [getattr(obj, method)(*args) for method, *args in case["ops"]]
                )
            else:
                fn = getattr(solution, function_name)
                got = isolated(lambda: fn(*case["args"]))
            if case.get("predicate"):
                passed = isolated(
                    lambda: CHECKERS[case["predicate"]](solution, got, case["args"])
                )
            else:
                passed = check_equal(got, expected, mode)
            printed = LAST["printed"]
            results.append(
                {
                    "label": label,
                    "passed": bool(passed),
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
                    "printed": LAST["printed"],
                    "elapsed_ms": (time.perf_counter() - t0) * 1000,
                }
            )
    _emit(results)


def _emit(results):
    """Write the protocol line with one `os.write` on the real fd 1.

    A single write cannot be interleaved with a print from a background thread,
    and the parent reads the last parseable line regardless."""
    blob = (json.dumps(results) + "\n").encode("utf-8", "replace")
    os.write(1, blob)


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


def _error_report(total: int, label: str, message: str) -> JudgeReport:
    return JudgeReport(
        status="error",
        total=total,
        passed=0,
        results=[
            CaseResult(
                label=label,
                passed=False,
                expected=None,
                got=None,
                error=message,
                elapsed_ms=0.0,
            )
        ],
    )


def run_cases(
    code_path: Path,
    function_name: str,
    cases: list[dict],
    timeout: float = 10.0,
    python: Path | str | None = None,
) -> JudgeReport:
    """Run ``cases`` against the code in ``code_path`` in a subprocess.

    Never raises for anything the child does: a timeout, a dead process, or an
    unreadable protocol each come back as a report. **An empty case list is
    refused** rather than graded as a pass — `all_passed` is true for zero cases,
    which once made an uncurated problem a free solve.
    """
    if not cases:
        return _error_report(
            0,
            "no cases",
            "refusing to grade: this problem has no cases (visible tests and a "
            "generator are both missing) — `dojo report <slug>` audits it",
        )
    with tempfile.TemporaryDirectory(prefix="dojo_judge_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "solution.py").write_text(code_path.read_text())
        (tmp_path / "cases.json").write_text(json.dumps(cases))
        (tmp_path / "harness.py").write_text(HARNESS)
        result = run_capped(
            [str(python or sys.executable), "harness.py", function_name],
            cwd=tmp_path,
            timeout=timeout,
        )
    if result.timed_out:
        return JudgeReport(status="timed_out", total=len(cases), passed=0)
    raw = last_json_object(result.stdout)
    if raw is None:
        detail = [
            line for line in (result.stderr or "").strip().splitlines() if line.strip()
        ]
        tail = " | ".join(detail[-3:])[:500]
        return _error_report(
            len(cases),
            "harness",
            tail
            or "the judge process produced no readable result (it may have been "
            "killed by a resource limit)",
        )
    if not isinstance(raw, list):
        return _error_report(len(cases), "harness", f"unexpected protocol payload: {raw!r}"[:200])
    results = [
        CaseResult(
            label=r.get("label", "?"),
            passed=bool(r.get("passed")),
            expected=r.get("expected"),
            got=r.get("got"),
            error=r.get("error"),
            elapsed_ms=r.get("elapsed_ms", 0.0),
            printed=r.get("printed", ""),
        )
        for r in raw
    ]
    n_passed = sum(1 for r in results if r.passed)
    if n_passed == len(results):
        status = "correct"
    elif any(r.error for r in results):
        # A crash is not a wrong answer: "my code raised" and "my logic is
        # wrong" are different coaching problems, and `error` used to be
        # unreachable for case-level failures.
        status = "error"
    else:
        status = "wrong_answer"
    return JudgeReport(
        status=status, results=results, total=len(results), passed=n_passed
    )
