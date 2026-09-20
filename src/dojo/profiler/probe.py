"""The paired scale probe.

Runs an implementation (or two) at a ladder of sizes in isolated subprocesses and
reports, per size: wall time, peak memory, the digest of the result, and — as
first-class data rather than a void — any exception or timeout.

This replaces `measure.py`. The differences that matter:

- **Failure is a result.** A code path that raises or hangs at n=400 is the most
  useful thing this feature can find; it used to be swallowed, leaving NULL
  columns and a 5/5 review for code that crashed at n=10.
- **The argument copy happens outside the timed window.** v0.11 timed
  `fn(*copy.deepcopy(args))`, so at n=6400 the copy was 0.769 ms of the 1.005 ms
  reported — 76% of the "algorithm time" was the profiler's own bookkeeping.
- **Two targets, interleaved.** Measuring the reference back-to-back with the
  student at each size makes machine drift common-mode, which is what lets the
  ratio in `growth.py` be compared at all.
- The ascent stops when a size fails (bigger is pointless once it breaks), and a
  timed-out size does not burn its remaining repeats.

The tracer is never active during the timed call, and each call gets a fresh
copy of the arguments so an in-place `sort()` cannot change what a later call
does.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dojo.proc import run_capped

#: ~6 doublings: enough for a one-class difference (n vs n log n) to show as a
#: ~1.9x ratio trend, without running an O(n^2) solution into the timeout.
DEFAULT_MAX_N = 6400
LADDER_POINTS = 7
DEFAULT_REPEATS = 3
DEFAULT_TIMEOUT = 20.0
SEED = 20240510

PROBE_HARNESS = r'''
import copy
import gc
import hashlib
import importlib.util
import json
import math
import random
import sys
import time
import tracemalloc

# Hard limits on this process before any user code is imported: the measurement
# subprocess runs the student's module, and a runaway loop must be contained by
# more than a wall clock (v0.13).
from dojo.proc import apply_child_limits

apply_child_limits()


def _identity_decorator(*args, **kwargs):
    def wrap(fn):
        return fn
    return wrap


# Registry decorators are no-ops here: the measured module may be a curated
# reference snippet, which carries its own @reference("slug") line. They must be
# injected into the *loaded module's* namespace — a decorated function resolves
# the decorator name in its own globals, not in ours.
NOOP_DECORATORS = ("oracle", "judge_case", "profiler_input", "checker", "reference")


def _canonical(value):
    """Deep-sort lists (and dicts by key) so 'any order' answers compare equal."""
    if isinstance(value, list):
        key = lambda v: json.dumps(v, sort_keys=True, default=str)
        return sorted((_canonical(v) for v in value), key=key)
    if isinstance(value, dict):
        return [(k, _canonical(v)) for k, v in sorted(value.items())]
    return value


def _digest(value, mode):
    if mode == "sorted":
        value = _canonical(value)
    blob = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest(), blob[:160]


def main():
    path, function_name, args_path, mode = (
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    )
    with open(args_path) as f:
        args = json.load(f)

    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # user prints must not corrupt the JSON channel
    out = {"ms": None, "peak": None, "digest": None, "preview": None, "error": None}
    try:
        spec = importlib.util.spec_from_file_location("measured", path)
        module = importlib.util.module_from_spec(spec)
        for _name in NOOP_DECORATORS:
            setattr(module, _name, _identity_decorator)
        try:
            spec.loader.exec_module(module)
        except BaseException as exc:
            out["error"] = f"import failed: {type(exc).__name__}: {exc}"
            return
        fn = getattr(module, function_name)

        # 1. warm-up: resolves first-call specialisation, timed by nothing.
        try:
            fn(*copy.deepcopy(args))
        except BaseException as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
            return

        # 2. the timed call. The copy is outside the window on purpose, and no
        # tracer may be running.
        try:
            payload = copy.deepcopy(args)
            gc.disable()
            t0 = time.perf_counter()
            result = fn(*payload)
            out["ms"] = (time.perf_counter() - t0) * 1e3
            gc.enable()
        except BaseException as exc:
            gc.enable()
            out["error"] = f"{type(exc).__name__}: {exc}"
            return

        out["digest"], out["preview"] = _digest(result, mode)

        # 3. space: tracemalloc runs here and only here, untimed.
        try:
            payload = copy.deepcopy(args)
            gc.collect()
            tracemalloc.start()
            base = tracemalloc.get_traced_memory()[0]
            fn(*payload)
            out["peak"] = tracemalloc.get_traced_memory()[1] - base
            tracemalloc.stop()
        except BaseException as exc:
            out["peak"] = None
    finally:
        sys.stdout = real_stdout
        print(json.dumps(out))


main()
'''


@dataclass
class Target:
    """One implementation under measurement."""

    label: str  # "yours" | "reference"
    path: Path
    function_name: str


@dataclass
class Run:
    ms: float | None = None
    peak: int | None = None
    digest: str | None = None
    preview: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ScalePoint:
    n: int
    student: Run
    reference: Run | None = None
    #: widest relative range across the repeats at this size (diagnostic only)
    spread: float = 0.0

    @property
    def time_ratio(self) -> float | None:
        if self.reference is None or not self.student.ok or not self.reference.ok:
            return None
        if not self.student.ms or not self.reference.ms:
            return None
        return self.student.ms / self.reference.ms

    @property
    def space_ratio(self) -> float | None:
        ref, stu = self.reference, self.student
        if ref is None or not stu.ok or not ref.ok:
            return None
        if not stu.peak or not ref.peak:
            return None
        return stu.peak / ref.peak

    @property
    def outputs_agree(self) -> bool | None:
        if self.reference is None or self.student.digest is None:
            return None
        if self.reference.digest is None:
            return None
        return self.student.digest == self.reference.digest


@dataclass
class Probe:
    points: list[ScalePoint] = field(default_factory=list)
    has_reference: bool = False

    @property
    def time_ratios(self) -> list[tuple[int, float | None]]:
        return [(p.n, p.time_ratio) for p in self.points]

    @property
    def space_ratios(self) -> list[tuple[int, float | None]]:
        return [(p.n, p.space_ratio) for p in self.points]

    def first_failure(self) -> ScalePoint | None:
        for point in self.points:
            if not point.student.ok:
                return point
        return None

    def reference_failure(self) -> ScalePoint | None:
        for point in self.points:
            if point.reference is not None and not point.reference.ok:
                return point
        return None

    def first_mismatch(self) -> ScalePoint | None:
        for point in self.points:
            if point.outputs_agree is False:
                return point
        return None


def ladder(max_n: int = DEFAULT_MAX_N, points: int = LADDER_POINTS) -> list[int]:
    """Doubling ladder ending at ``max_n``."""
    sizes = [max_n]
    while len(sizes) < points:
        sizes.append(sizes[-1] // 2)
    return sorted(sizes)


def run_one(
    target: Target,
    args: list,
    timeout: float = DEFAULT_TIMEOUT,
    compare: str = "strict",
) -> Run:
    """Measure one target on one input, in its own subprocess.

    Output is bounded on the parent's side too: user prints are routed to stderr
    inside the harness, and reading that stream with ``capture_output=True`` used
    to let a hot print loop grow *dojo's own* memory to ~1.75 GB (v0.13)."""
    with tempfile.TemporaryDirectory(prefix="dojo_probe_") as tmp:
        tmp_path = Path(tmp)
        harness = tmp_path / "harness.py"
        harness.write_text(PROBE_HARNESS)
        args_path = tmp_path / "args.json"
        args_path.write_text(json.dumps(args))
        result = run_capped(
            [
                sys.executable,
                str(harness),
                str(target.path),
                target.function_name,
                str(args_path),
                compare,
            ],
            cwd=tmp_path,
            timeout=timeout,
        )
        if result.timed_out:
            return Run(error=f"timed out after {timeout:g}s")
        if not result.stdout.strip():
            detail = [line for line in result.stderr.strip().splitlines() if line.strip()]
            tail = detail[-1][:200] if detail else "no output"
            return Run(error=f"the measurement process died ({tail})")
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return Run(error="the measurement process produced unreadable output")
        return Run(
            ms=payload.get("ms"),
            peak=payload.get("peak"),
            digest=payload.get("digest"),
            preview=payload.get("preview"),
            error=payload.get("error"),
        )


def _median_run(runs: list[Run]) -> tuple[Run, float]:
    """The representative run for one size: median time, median peak, plus the
    observed spread (max-min over the median) as a diagnostic."""
    ok = [r for r in runs if r.ok and r.ms is not None]
    if not ok:
        return runs[0], 0.0
    times = sorted(r.ms for r in ok)
    mid = times[len(times) // 2]
    spread = (times[-1] - times[0]) / mid if mid else 0.0
    chosen = next(r for r in ok if r.ms == mid)
    peaks = sorted(r.peak for r in ok if r.peak is not None)
    return (
        Run(
            ms=mid,
            peak=peaks[len(peaks) // 2] if peaks else None,
            digest=chosen.digest,
            preview=chosen.preview,
        ),
        spread,
    )


def run_probe(
    student: Target,
    generator: Callable[[int, random.Random], list],
    reference: Target | None = None,
    *,
    sizes: list[int] | None = None,
    repeats: int = DEFAULT_REPEATS,
    timeout: float = DEFAULT_TIMEOUT,
    compare: str = "strict",
) -> Probe:
    """Measure ``student`` (and ``reference``, interleaved) across the ladder.

    The ascent stops at the first size where either side fails: a solution that
    breaks at n=400 tells us nothing more at n=3200, and a reference that cannot
    run at n=3200 cannot be compared against.
    """
    sizes = sizes or ladder()
    rng = random.Random(SEED)
    result = Probe(has_reference=reference is not None)
    for n in sizes:
        args = generator(n, rng)
        student_runs: list[Run] = []
        reference_runs: list[Run] = []
        for _ in range(repeats):
            run = run_one(student, args, timeout, compare)
            student_runs.append(run)
            if reference is not None:
                reference_runs.append(run_one(reference, args, timeout, compare))
            if not run.ok:
                break  # do not burn the remaining repeats on a failure
        student_run, spread = _median_run(student_runs)
        reference_run = _median_run(reference_runs)[0] if reference_runs else None
        result.points.append(
            ScalePoint(n=n, student=student_run, reference=reference_run, spread=spread)
        )
        if not student_run.ok:
            break
        if reference_run is not None and not reference_run.ok:
            break
    return result


def locate_mismatch(
    student: Target,
    reference: Target,
    generator: Callable[[int, random.Random], list],
    above: int,
    *,
    floor: int = 10,
    steps: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
    compare: str = "strict",
) -> int:
    """The smallest tested size at which the two implementations disagree.

    ``above`` is a size already known to disagree (the probe stops ascending at
    the first one). Walking back down turns "differs at n=6400" into something a
    student can actually reason about, and it is bounded: small inputs are where
    a counterexample is most useful and where each run is cheapest. Returns
    ``above`` when no smaller size disagrees."""
    smallest = above
    n = above // 2
    for _ in range(steps):
        if n < floor:
            break
        args = generator(n, random.Random(SEED))
        got = run_one(student, args, timeout, compare)
        want = run_one(reference, args, timeout, compare)
        if not got.ok or not want.ok or got.digest is None or want.digest is None:
            break  # the comparison is undefined here; keep the size we have
        if got.digest == want.digest:
            break  # they agree here, so the boundary is above this size
        smallest = n
        n //= 2
    return smallest
