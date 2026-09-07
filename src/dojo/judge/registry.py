"""Registries for oracles, judge-case generators, and profiler inputs.

ORACLES ARE REFERENCE IMPLEMENTATIONS. They exist only to produce expected
outputs for correctness testing. Never feed oracle code to the tutor agent —
the never-solve guarantee depends on reference solutions staying out of the
tutor's context.
"""

from __future__ import annotations

import random
from typing import Any, Callable

#: slug -> callable(*args) -> expected output (a brute-force reference).
ORACLES: dict[str, Callable[..., Any]] = {}

#: slug -> (n, rng) -> (args, expected): small random correctness cases.
JUDGE_CASES: dict[str, Callable[[int, random.Random], tuple[list, Any]]] = {}

#: slug -> (n, rng) -> args: inputs of size ~n for complexity measurement.
#: These must exercise worst-case-ish paths, not early exits — a random
#: bracket string fails at the first unmatched closer, which would make an
#: O(n) solution *measure* as O(1).
PROFILER_INPUTS: dict[str, Callable[[int, random.Random], list]] = {}


def oracle(slug: str) -> Callable[..., Any]:
    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        ORACLES[slug] = fn
        return fn

    return register


def judge_case(slug: str) -> Callable:
    def register(fn) -> Callable:
        JUDGE_CASES[slug] = fn
        return fn

    return register


def profiler_input(slug: str) -> Callable:
    def register(fn) -> Callable:
        PROFILER_INPUTS[slug] = fn
        return fn

    return register


# ---------------------------------------------------------------- built-ins


@oracle("valid_parentheses")
def _valid_parentheses_oracle(s: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            return False
    return not stack


@judge_case("valid_parentheses")
def _valid_parentheses_case(n: int, rng: random.Random) -> tuple[list, bool]:
    """Random bracket strings of length n; half the time start from a valid
    string and mutate it, to guarantee coverage of near-valid inputs."""
    alphabet = "()[]{}"
    if n <= 0:
        return [""], _valid_parentheses_oracle("")
    if rng.random() < 0.5:
        # Build a valid string from k matched pairs, then mutate one char.
        k = max(1, n // 2)
        openers, closers = "([{", ")]}"
        parts = []
        for _ in range(k):
            i = rng.randrange(3)
            parts.append(openers[i] + closers[i])
        s = list("".join(parts))
        if rng.random() < 0.7 and s:
            pos = rng.randrange(len(s))
            s[pos] = rng.choice(alphabet)
        s = "".join(s[:n])
    else:
        s = "".join(rng.choice(alphabet) for _ in range(n))
    return [s], _valid_parentheses_oracle(s)


@profiler_input("valid_parentheses")
def _valid_parentheses_profiler_input(n: int, rng: random.Random) -> list:
    """n nested opens then n closes: valid, scans the whole string, stack
    grows to depth n. Guarantees the O(n) path, never an early exit."""
    return ["(" * n + ")" * n]
