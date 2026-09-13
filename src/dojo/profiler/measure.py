"""Measurement: wall-time and tracemalloc space across doubling input sizes.

Each (size, repeat) runs in its own subprocess — one measurement per process,
so module import costs and cross-call GC noise stay out of the numbers.
Medians across repeats resist outliers; the fit (see fit.py) does the
classification.

Instrument separation (v0.11). Inside each subprocess three calls happen, in
this order:

1. an untimed warm-up call, which resolves first-call bytecode specialisation
   before anything is measured;
2. **the timed call, with no tracer running**;
3. the space call, with tracemalloc active and no timer.

The order is the point. tracemalloc's per-allocation bookkeeping is itself
superlinear, so running it underneath the timer does not measure the
algorithm — it measures the instrument. That is what made allocation-heavy
O(n) code report O(n log n): on one real solution the slope was 1.164 with
tracing and 0.889 without.

Every call runs on a fresh deep copy of the arguments, so a solution that
mutates its input in place (a sort, a seen-set) cannot make later calls do
different work than the first.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MEASURE_SCRIPT = r'''
import copy
import gc
import importlib.util
import json
import sys
import time
import tracemalloc


def main():
    function_name, args_path = sys.argv[1], sys.argv[2]
    with open(args_path) as f:
        args = json.load(f)
    spec = importlib.util.spec_from_file_location("solution", "solution.py")
    solution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(solution)
    fn = getattr(solution, function_name)

    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # user prints must not corrupt the JSON channel

    def call():
        # A fresh copy per call: an in-place sort must not change the work the
        # next call does, or the measurements would describe different jobs.
        return fn(*copy.deepcopy(args))

    try:
        call()  # untimed, untraced: warm the code paths first

        gc.disable()
        t0 = time.perf_counter()
        call()  # THE timed call — no tracer may be running here
        elapsed_ms = (time.perf_counter() - t0) * 1e3
        gc.enable()

        # Space is measured separately and is never timed. tracemalloc stays
        # out of the timed region above on purpose.
        gc.collect()
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        before = tracemalloc.take_snapshot()
        call()
        after = tracemalloc.take_snapshot()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        sys.stdout = real_stdout

    net = sum(stat.size_diff for stat in after.compare_to(before, "filename"))
    print(json.dumps({"elapsed_ms": elapsed_ms, "net_bytes": net, "peak_bytes": peak - base}))


if __name__ == "__main__":
    main()
'''

DEFAULT_SIZES = [100, 200, 400, 800, 1600, 3200, 6400]
DEFAULT_REPEATS = 5
DEFAULT_TIMEOUT = 20.0


@dataclass
class Measurement:
    sizes: list[int]
    times_ms: list[float | None] = field(default_factory=list)   # median per size
    space_bytes: list[float | None] = field(default_factory=list)  # median per size
    dropped: list[str] = field(default_factory=list)  # human notes
    #: The widest run-to-run relative range seen at any size ((max-min)/median).
    #: The fit turns this into the noise floor below which two candidate
    #: complexity classes cannot be told apart.
    spread: float = 0.0

    @property
    def time_points(self) -> list[tuple[int, float]]:
        return [
            (n, t) for n, t in zip(self.sizes, self.times_ms) if t is not None
        ]

    @property
    def space_points(self) -> list[tuple[int, float]]:
        return [
            (n, s) for n, s in zip(self.sizes, self.space_bytes) if s is not None
        ]


def _run_once(
    code_path: Path, function_name: str, args: list, timeout: float
) -> dict | None:
    with tempfile.TemporaryDirectory(prefix="dojo_measure_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "solution.py").write_text(code_path.read_text())
        args_path = tmp_path / "args.json"
        args_path.write_text(json.dumps(args))
        try:
            proc = subprocess.run(
                [sys.executable, "-c", MEASURE_SCRIPT, function_name, str(args_path)],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None


def _relative_spread(samples: list[float]) -> float:
    """(max - min) / median — the observed run-to-run range at one size."""
    if len(samples) < 2:
        return 0.0
    median = samples[len(samples) // 2]
    if median <= 0:
        return 0.0
    return (samples[-1] - samples[0]) / median


def measure(
    code_path: Path,
    function_name: str,
    input_generator: Callable[[int, random.Random], list],
    sizes: list[int] = DEFAULT_SIZES,
    repeats: int = DEFAULT_REPEATS,
    timeout: float = DEFAULT_TIMEOUT,
) -> Measurement:
    rng = random.Random(20240510)  # deterministic across runs
    result = Measurement(sizes=sizes)
    for n in sizes:
        times, spaces = [], []
        for _ in range(repeats):
            args = input_generator(n, rng)
            out = _run_once(code_path, function_name, args, timeout)
            if out is None:
                continue
            times.append(out["elapsed_ms"])
            spaces.append(float(out["peak_bytes"]))
        if not times:
            result.dropped.append(f"n={n}: all repeats timed out or failed")
            result.times_ms.append(None)
            result.space_bytes.append(None)
            continue
        times.sort()
        spaces.sort()
        result.spread = max(result.spread, _relative_spread(times) / 2.0)
        if len(times) < repeats:
            result.dropped.append(f"n={n}: {len(times)}/{repeats} repeats")
        result.times_ms.append(times[len(times) // 2])
        result.space_bytes.append(spaces[len(spaces) // 2])
    return result
