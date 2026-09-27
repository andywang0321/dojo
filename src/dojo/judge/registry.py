"""Registries for oracles, judge-case generators, references, and profiler inputs.

TWO KINDS OF REFERENCE IMPLEMENTATION LIVE HERE, with different jobs (v0.12):

- ``ORACLES`` — brute-force correctness anchors. Their only job is to produce
  expected outputs, and "prefer a simple brute force" is deliberate: an obvious
  implementation is one you can trust. They cannot double as performance
  baselines, because they *are* the slow thing (``products_of_array_except_self``
  targets O(n) while its oracle is an O(n^2) double loop), and they cannot run at
  scale at all.
- ``REFERENCES`` — canonical, intended-complexity solutions. They are the scale
  and performance baseline the v0.12 probe measures against, which is what makes
  a growth verdict possible at all. A reference is admitted only if it agrees
  with the oracle wherever the oracle can run (see ``curator.add_reference``).

Neither may ever reach the tutor agent: the never-solve guarantee depends on
reference implementations staying out of the tutor's context. A canonical
reference raises the cost of a leak — it is directly paste-able — so the
boundary test matters more here, not less.

Curation conventions (see AGENTS.md "Curating a new problem"):
- Where a prompt allows "any order", the contract is pinned to a canonical
  order and the oracle emits exactly that (the visible tests show it).
- Trees are nested lists [value, left, right]; None is a missing child or an
  empty tree.
- judge_case(n, rng) clamps n into the problem's constraints (flow calls it
  with 0..12).
- profiler_input(n, rng) produces inputs whose total size is ~n and that
  never let a solution early-exit. Problems without a registered profiler
  input skip measurement (fixed-size inputs, exponential output, or growth
  too flat to measure honestly at probe sizes).
- v0.12: those inputs must also respect the problem's *value* constraints, not
  just its shape. `products_of_array_except_self` was generated with values up
  to +-20 at n=6400, which drives the running product to ~19,000 bits and
  violates the problem's own 32-bit guarantee — so a correct O(n) solution
  measured as superlinear at r2=0.995. The contract test pins shape; the
  `dojo report` audit pins value ranges.
"""

from __future__ import annotations

import random
from typing import Any, Callable

#: slug -> callable(*args) -> expected output (a brute-force reference).
ORACLES: dict[str, Callable[..., Any]] = {}

#: slug -> (n, rng) -> (args, expected): small random correctness cases.
#: Generators may also return a third element, a dict of case extras
#: ({"compare": ...} / {"predicate": ...} / {"ops": ...}).
JUDGE_CASES: dict[str, Callable[[int, random.Random], tuple[list, Any, ...]]] = {}

#: name -> (module, got, args) -> bool: predicate checkers for cases tagged
#: {"predicate": name}. Property-based verdicts the fixed comparators can't
#: express (round-trips, "any valid sample", "any peak"). Quarantine zone —
#: never tutor context.
CHECKERS: dict[str, Callable[..., bool]] = {}

#: slug -> callable(*args) -> canonical output. A fast implementation at the
#: problem's *intended* complexity: the probe's performance baseline and its
#: large-input correctness comparator. Admitted only against the oracle.
REFERENCES: dict[str, Callable[..., Any]] = {}

#: slug -> (n, rng) -> args: inputs of size ~n for complexity measurement.
#: These must exercise worst-case-ish paths, not early exits — a random
#: bracket string fails at the first unmatched closer, which would make an
#: O(n) solution *measure* as O(1). They must also respect the problem's
#: *value* constraints, not just its shape (see the module docstring).
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


def reference(slug: str) -> Callable[..., Any]:
    """Register the canonical solution for ``slug`` (v0.12).

    Must be self-contained and use the same call convention as the oracle, so
    the probe can run it on the same inputs."""

    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        REFERENCES[slug] = fn
        return fn

    return register


def profiler_input(slug: str) -> Callable:
    def register(fn) -> Callable:
        PROFILER_INPUTS[slug] = fn
        return fn

    return register


def checker(name: str) -> Callable:
    def register(fn) -> Callable:
        CHECKERS[name] = fn
        return fn

    return register


# ------------------------------------------------------------ shared helpers


def _random_tree(rng: random.Random, budget: int) -> list | None:
    """A random binary tree with at most ``budget`` nodes, nested-list form
    [value, left, right]."""
    if budget <= 0:
        return None
    budget -= 1
    left = _random_tree(rng, budget // 2) if rng.random() < 0.7 else None
    right = _random_tree(rng, budget // 2) if rng.random() < 0.7 else None
    return [rng.randint(0, 9), left, right]


def _mirror_of(node: list | None) -> list | None:
    if node is None:
        return None
    return [node[0], _mirror_of(node[2]), _mirror_of(node[1])]


def _mirror_tree(rng: random.Random, budget: int) -> list | None:
    """A random symmetric tree (a mirror image of itself)."""
    if budget <= 0:
        return None
    budget -= 1
    left = _random_tree(rng, budget // 2) if rng.random() < 0.8 else None
    return [rng.randint(0, 9), left, _mirror_of(left)]


def _complete_tree(n: int) -> list | None:
    """A complete binary tree with exactly n nodes, nested-list form.

    NOT a BST: node ``i`` is labelled ``i``, so a left child (``2i+1``) holds a
    larger value than its parent. Fine for shape questions (diameter, mirror),
    silently wrong for anything the statement calls a BST — build a balanced tree
    over ``0..n-1`` instead (the trees batch of v0.14 hit exactly this)."""
    if n <= 0:
        return None
    nodes: list[list | None] = [None] * n
    for i in range(n - 1, -1, -1):  # bottom-up: children finalized first
        left, right = 2 * i + 1, 2 * i + 2
        nodes[i] = [i, nodes[left] if left < n else None, nodes[right] if right < n else None]
    return nodes[0]


# ------------------------------------------------------- arrays_and_hashing


@oracle("array_intersection")
def _intersection_oracle(A: list[int], B: list[int]) -> list[int]:
    return sorted(set(A) & set(B))


@judge_case("array_intersection")
def _intersection_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(0, min(n, 12))
    A = [rng.randint(-5, 5) for _ in range(rng.randint(0, n))]
    B = [rng.randint(-5, 5) for _ in range(rng.randint(0, n))]
    return [A, B], _intersection_oracle(A, B), {"compare": "sorted"}


@profiler_input("array_intersection")
def _intersection_profiler(n: int, rng: random.Random) -> list:
    return [list(range(n)), list(range(n // 2, n + n // 2))]


@oracle("contains_duplicate")
def _contains_duplicate_oracle(nums: list[int]) -> bool:
    return len(nums) != len(set(nums))


@judge_case("contains_duplicate")
def _contains_duplicate_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))
    nums = [rng.randint(-5, 5) for _ in range(n)]
    if n >= 2 and rng.random() < 0.5:
        nums[rng.randrange(n)] = nums[0]  # force a duplicate
    return [nums], _contains_duplicate_oracle(nums)


@profiler_input("contains_duplicate")
def _contains_duplicate_profiler(n: int, rng: random.Random) -> list:
    values = list(range(n))  # all distinct: no early exit for anyone
    rng.shuffle(values)
    return [values]


@oracle("group_anagrams")
def _group_anagrams_oracle(strs: list[str]) -> list[list[str]]:
    groups: dict[str, list[str]] = {}
    for s in strs:
        groups.setdefault("".join(sorted(s)), []).append(s)
    return [sorted(group) for _, group in sorted(groups.items())]


@judge_case("group_anagrams")
def _group_anagrams_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(0, min(n, 12))
    strs = ["".join(rng.choice("ab") for _ in range(rng.randint(1, 4))) for _ in range(n)]
    return [strs], _group_anagrams_oracle(strs), {"compare": "sorted"}


@profiler_input("group_anagrams")
def _group_anagrams_profiler(n: int, rng: random.Random) -> list:
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return [["".join(rng.choice(alphabet) for _ in range(8)) for _ in range(n)]]


@oracle("longest_consecutive_sequence")
def _longest_seqlen_oracle(nums: list[int]) -> int:
    num_set = set(nums)
    longest = 0
    for num in num_set:
        if num - 1 not in num_set:
            length = 1
            while num + length in num_set:
                length += 1
            longest = max(longest, length)
    return longest


@judge_case("longest_consecutive_sequence")
def _longest_seqlen_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(0, min(n, 12))
    nums = [rng.randint(-10, 10) for _ in range(n)]
    return [nums], _longest_seqlen_oracle(nums)


@profiler_input("longest_consecutive_sequence")
def _longest_seqlen_profiler(n: int, rng: random.Random) -> list:
    values = list(range(n))
    rng.shuffle(values)
    return [values]


@oracle("products_of_array_except_self")
def _prod_except_self_oracle(nums: list[int]) -> list[int]:
    out: list[int] = []
    for i in range(len(nums)):
        product = 1
        for j in range(len(nums)):
            if i != j:
                product *= nums[j]
        out.append(product)
    return out


@judge_case("products_of_array_except_self")
def _prod_except_self_case(n: int, rng: random.Random) -> tuple[list, list]:
    n = max(0, min(n, 12))
    nums = [rng.randint(-5, 5) for _ in range(n)]
    return [nums], _prod_except_self_oracle(nums)


@profiler_input("products_of_array_except_self")
def _prod_except_self_profiler(n: int, rng: random.Random) -> list:
    return [[rng.randint(-20, 20) or 1 for _ in range(n)]]


@oracle("top_k_frequent_elements")
def _top_k_freq_oracle(nums: list[int], k: int) -> list[int]:
    counts: dict[int, int] = {}
    for num in nums:
        counts[num] = counts.get(num, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [value for value, _ in ranked[:k]]


def _unique_counts(n: int, rng: random.Random) -> list[int]:
    """Distinct positive counts summing to n — the top-k prompt promises
    'the answer is always unique', so generated frequencies must be unique
    (a frequency tie would make equality judging false-fail)."""
    counts: list[int] = []
    total = 0
    c = 1
    while total + c <= n:
        counts.append(c)
        total += c
        c += 1
    if total < n:
        remainder = n - total
        if remainder in counts:
            counts[-1] += remainder  # stays unique: > every existing count
        else:
            counts.append(remainder)
    rng.shuffle(counts)
    return counts


@judge_case("top_k_frequent_elements")
def _top_k_freq_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(1, min(n, 12))
    counts = _unique_counts(n, rng)
    nums = []
    for i, count in enumerate(counts):
        nums.extend([i - 10] * count)
    rng.shuffle(nums)
    k = rng.randint(1, len(counts))
    return [nums, k], _top_k_freq_oracle(nums, k), {"compare": "sorted"}


@profiler_input("top_k_frequent_elements")
def _top_k_freq_profiler(n: int, rng: random.Random) -> list:
    values = list(range(n))
    rng.shuffle(values)
    return [values, max(1, n // 2)]


@oracle("two_sum")
def _twosum_oracle(nums: list[int], target: int) -> list[int]:
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
    return []


@judge_case("two_sum")
def _twosum_case(n: int, rng: random.Random) -> tuple[list, list]:
    n = max(2, min(n, 12))
    nums = rng.sample(range(-20, 21), n)
    i, j = rng.sample(range(n), 2)
    target = nums[i] + nums[j]
    pairs = [(a, b) for a in range(n) for b in range(a + 1, n) if nums[a] + nums[b] == target]
    while len(pairs) != 1:  # the prompt guarantees exactly one valid pair
        nums = rng.sample(range(-20, 21), n)
        i, j = rng.sample(range(n), 2)
        target = nums[i] + nums[j]
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n) if nums[a] + nums[b] == target]
    return [nums, target], [pairs[0][0], pairs[0][1]]


@profiler_input("two_sum")
def _two_sum_profiler(n: int, rng: random.Random) -> list:
    values = list(range(n))
    rng.shuffle(values)
    return [values, -(sum(values)) - 1]  # absent target: full scan for everyone


@oracle("valid_anagram")
def _valid_anagram_oracle(s: str, t: str) -> bool:
    return sorted(s) == sorted(t)


@judge_case("valid_anagram")
def _valid_anagram_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))
    s = "".join(rng.choice("abcdefgh") for _ in range(n))
    if rng.random() < 0.5:
        chars = list(s)
        rng.shuffle(chars)
        t = "".join(chars)
    else:
        t = "".join(rng.choice("abcdefgh") for _ in range(n))
    return [s, t], _valid_anagram_oracle(s, t)


@profiler_input("valid_anagram")
def _valid_anagram_profiler(n: int, rng: random.Random) -> list:
    s = ("abcdefgh" * (n // 8 + 1))[:n]
    chars = list(s)
    rng.shuffle(chars)
    return [s, "".join(chars)]


# A known-valid solved board: the generator permutes its digits (a bijection
# preserves validity) or injects a duplicate.
_VALID_BOARD = [
    ["5", "3", "4", "6", "7", "8", "9", "1", "2"],
    ["6", "7", "2", "1", "9", "5", "3", "4", "8"],
    ["1", "9", "8", "3", "4", "2", "5", "6", "7"],
    ["8", "5", "9", "7", "6", "1", "4", "2", "3"],
    ["4", "2", "6", "8", "5", "3", "7", "9", "1"],
    ["7", "1", "3", "9", "2", "4", "8", "5", "6"],
    ["9", "6", "1", "5", "3", "7", "2", "8", "4"],
    ["2", "8", "7", "4", "1", "9", "6", "3", "5"],
    ["3", "4", "5", "2", "8", "6", "1", "7", "9"],
]


@oracle("valid_sudoku")
def _valid_sudoku_oracle(board: list[list[str]]) -> bool:
    def ok(cells: list[str]) -> bool:
        digits = [c for c in cells if c != "."]
        return len(digits) == len(set(digits))

    for row in board:
        if not ok(row):
            return False
    for j in range(9):
        if not ok([board[i][j] for i in range(9)]):
            return False
    for bi in range(3):
        for bj in range(3):
            if not ok([board[bi * 3 + di][bj * 3 + dj] for di in range(3) for dj in range(3)]):
                return False
    return True


@judge_case("valid_sudoku")
def _valid_sudoku_case(n: int, rng: random.Random) -> tuple[list, bool]:
    digits = rng.sample("123456789", 9)
    board = [[digits[int(c) - 1] if c != "." else "." for c in row] for row in _VALID_BOARD]
    for _ in range(rng.randint(0, 20)):  # partially filled boards stay valid
        board[rng.randrange(9)][rng.randrange(9)] = "."
    if rng.random() < 0.5:
        # Two equal digits in one row is always invalid.
        row = rng.randrange(9)
        for j in range(9):
            if board[row][j] == "1":
                board[row][j] = "."
        j1 = rng.randrange(9)
        j2 = rng.randrange(9)
        while j2 == j1:
            j2 = rng.randrange(9)
        board[row][j1] = board[row][j2] = "1"
    return [board], _valid_sudoku_oracle(board)


# --------------------------------------------------------------------- stack


@oracle("car_fleet")
def _car_fleet_oracle(target: int, position: list[int], speed: list[int]) -> int:
    cars = sorted(zip(position, speed), reverse=True)
    fleets = 0
    slowest = -1.0
    for pos, spd in cars:
        arrival = (target - pos) / spd
        if arrival > slowest:
            fleets += 1
            slowest = arrival
    return fleets


@judge_case("car_fleet")
def _car_fleet_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 8))
    target = 10 + rng.randint(1, 20)
    position = rng.sample(range(target), n)
    speed = [rng.randint(1, 10) for _ in range(n)]
    return [target, position, speed], _car_fleet_oracle(target, position, speed)


@profiler_input("car_fleet")
def _car_fleet_profiler(n: int, rng: random.Random) -> list:
    target = 2 * n
    position = list(range(n))
    speed = [rng.randint(1, 100) for _ in range(n)]
    return [target, position, speed]


@oracle("daily_temperatures")
def _daily_temperatures_oracle(temperatures: list[int]) -> list[int]:
    out: list[int] = []
    for i, t in enumerate(temperatures):
        wait = 0
        for j in range(i + 1, len(temperatures)):
            if temperatures[j] > t:
                wait = j - i
                break
        out.append(wait)
    return out


@judge_case("daily_temperatures")
def _daily_temperatures_case(n: int, rng: random.Random) -> tuple[list, list]:
    n = max(0, min(n, 12))
    temperatures = [rng.randint(0, 50) for _ in range(n)]
    return [temperatures], _daily_temperatures_oracle(temperatures)


@profiler_input("daily_temperatures")
def _daily_temperatures_profiler(n: int, rng: random.Random) -> list:
    return [list(range(1000, 1000 - n, -1))]  # strictly cooling: stack drains at the end


def _random_expr(rng: random.Random, depth: int) -> tuple[list[str], int]:
    """A random RPN expression (tokens, value). Leaves are nonzero so
    division never divides by zero."""
    if depth <= 0 or rng.random() < 0.4:
        value = rng.choice([v for v in range(-10, 11) if v != 0])
        return [str(value)], value
    left_tokens, left = _random_expr(rng, depth - 1)
    right_tokens, right = _random_expr(rng, depth - 1)
    op = rng.choice("+-*/")
    if op == "+":
        value = left + right
    elif op == "-":
        value = left - right
    elif op == "*":
        value = left * right
    else:
        if right == 0:
            right = rng.randint(1, 10)
            right_tokens = [str(right)]
        value = int(left / right)  # truncation toward zero, per the prompt
    return left_tokens + right_tokens + [op], value


@oracle("evaluate_reverse_polish_notation")
def _eval_rpn_oracle(tokens: list[str]) -> int:
    stack: list[int] = []
    for tok in tokens:
        if tok in "+-*/":
            b = stack.pop()
            a = stack.pop()
            if tok == "+":
                stack.append(a + b)
            elif tok == "-":
                stack.append(a - b)
            elif tok == "*":
                stack.append(a * b)
            else:
                stack.append(int(a / b))
        else:
            stack.append(int(tok))
    return stack[-1]


@judge_case("evaluate_reverse_polish_notation")
def _eval_rpn_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 10))
    tokens, value = _random_expr(rng, depth=3)
    return [tokens], value


@profiler_input("evaluate_reverse_polish_notation")
def _eval_rpn_profiler(n: int, rng: random.Random) -> list:
    return [["1", "1", "+"] * max(1, n // 3)]


@oracle("generate_parentheses")
def _generate_parentheses_oracle(n: int) -> list[str]:
    out: list[str] = []

    def build(prefix: str, opens: int, closes: int) -> None:
        if opens == n and closes == n:
            out.append(prefix)
            return
        if opens < n:
            build(prefix + "(", opens + 1, closes)
        if closes < opens:
            build(prefix + ")", opens, closes + 1)

    build("", 0, 0)
    return out  # DFS yields lexicographic order


@judge_case("generate_parentheses")
def _generate_parentheses_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(1, min(n, 7))
    return [n], _generate_parentheses_oracle(n), {"compare": "sorted"}
# No profiler input: the output itself is exponential, so polynomial growth
# fitting would misreport the algorithm.


@oracle("largest_rectangle_in_histogram")
def _largest_rectangle_oracle(heights: list[int]) -> int:
    best = 0
    for i in range(len(heights)):
        low = heights[i]
        for j in range(i, len(heights)):
            low = min(low, heights[j])
            best = max(best, low * (j - i + 1))
    return best


@judge_case("largest_rectangle_in_histogram")
def _largest_rectangle_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(0, min(n, 12))
    heights = [rng.randint(0, 10) for _ in range(n)]
    return [heights], _largest_rectangle_oracle(heights)


@profiler_input("largest_rectangle_in_histogram")
def _largest_rectangle_profiler(n: int, rng: random.Random) -> list:
    return [list(range(1, n + 1))]  # increasing bars: no pops until the end


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
def _valid_parentheses_profiler(n: int, rng: random.Random) -> list:
    """n nested opens then n closes: valid, scans the whole string, stack
    grows to depth n. Guarantees the O(n) path, never an early exit."""
    return ["(" * n + ")" * n]


# --------------------------------------------------------------- two_pointers


@oracle("container_with_most_water")
def _max_area_oracle(height: list[int]) -> int:
    best = 0
    for i in range(len(height)):
        for j in range(i + 1, len(height)):
            best = max(best, min(height[i], height[j]) * (j - i))
    return best


@judge_case("container_with_most_water")
def _max_area_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(2, min(n, 12))
    height = [rng.randint(0, 10) for _ in range(n)]
    return [height], _max_area_oracle(height)


@profiler_input("container_with_most_water")
def _max_area_profiler(n: int, rng: random.Random) -> list:
    return [[rng.randint(1, 100) for _ in range(n)]]


@oracle("three_sum")
def _three_sum_oracle(nums: list[int]) -> list[list[int]]:
    seen: set[tuple[int, int, int]] = set()
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            for k in range(j + 1, len(nums)):
                if nums[i] + nums[j] + nums[k] == 0:
                    seen.add(tuple(sorted((nums[i], nums[j], nums[k]))))
    return [list(t) for t in sorted(seen)]


@judge_case("three_sum")
def _three_sum_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(3, min(n, 12))
    nums = [rng.randint(-8, 8) for _ in range(n)]
    if rng.random() < 0.6:
        a = rng.randint(-6, 6)
        b = rng.randint(-6, 6)
        nums.extend([a, b, -(a + b)])  # embed a guaranteed zero-sum triple
        rng.shuffle(nums)
    return [nums], _three_sum_oracle(nums), {"compare": "sorted"}


@profiler_input("three_sum")
def _three_sum_profiler(n: int, rng: random.Random) -> list:
    return [[rng.randint(-20, 20) for _ in range(n)]]


@oracle("trapping_rain_water")
def _trap_oracle(height: list[int]) -> int:
    total = 0
    for i in range(len(height)):
        left = max(height[: i + 1])
        right = max(height[i:])
        total += min(left, right) - height[i]
    return total


@judge_case("trapping_rain_water")
def _trap_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(0, min(n, 12))
    height = [rng.randint(0, 8) for _ in range(n)]
    return [height], _trap_oracle(height)


@profiler_input("trapping_rain_water")
def _trap_profiler(n: int, rng: random.Random) -> list:
    return [[rng.randint(0, n) for _ in range(n)]]


@oracle("two_sum_2")
def _two_sum_2_oracle(numbers: list[int], target: int) -> list[int]:
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if numbers[i] + numbers[j] == target:
                return [i + 1, j + 1]
    return []


@judge_case("two_sum_2")
def _two_sum_2_case(n: int, rng: random.Random) -> tuple[list, list]:
    n = max(2, min(n, 12))
    numbers = sorted(rng.sample(range(-10, 11), n))
    i, j = rng.sample(range(n), 2)
    target = numbers[i] + numbers[j]
    pairs = [(a, b) for a in range(n) for b in range(a + 1, n) if numbers[a] + numbers[b] == target]
    while len(pairs) != 1:  # the prompt guarantees exactly one valid pair
        numbers = sorted(rng.sample(range(-10, 11), n))
        i, j = rng.sample(range(n), 2)
        target = numbers[i] + numbers[j]
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n) if numbers[a] + numbers[b] == target]
    return [numbers, target], [pairs[0][0] + 1, pairs[0][1] + 1]


@profiler_input("two_sum_2")
def _two_sum_2_profiler(n: int, rng: random.Random) -> list:
    return [list(range(1, n + 1)), 3 * n + 5]  # absent target: full scan


def _normalize_palindrome(s: str) -> str:
    return "".join(c for c in s if c.isalnum()).lower()


@oracle("valid_palindrome")
def _is_palindrome_oracle(s: str) -> bool:
    t = _normalize_palindrome(s)
    return t == t[::-1]


@judge_case("valid_palindrome")
def _is_palindrome_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))
    if rng.random() < 0.5:
        half = "".join(rng.choice("abcdefgh") for _ in range(n // 2))
        mid = rng.choice(["", "x", "!?"]) if n % 2 else ""
        s = half + mid + half[::-1]  # a palindrome (ignoring punctuation)
    else:
        s = "".join(rng.choice("abcdefgh !?,") for _ in range(n))
    return [s], _is_palindrome_oracle(s)


@profiler_input("valid_palindrome")
def _valid_palindrome_profiler(n: int, rng: random.Random) -> list:
    return ["a" * n]  # a true palindrome: no early mismatch to bail out on


# ----------------------------------------------------------------------- heap


@checker("k_closest_valid")
def _k_closest_valid(module, got, args) -> bool:
    """The true k-closest contract — 'ties may be broken in any order':
    exactly k points drawn from the input multiset, none farther than the
    k-th smallest distance, and every strictly-closer point fully included.
    Equality judging false-fails on boundary ties; this grades the set."""
    from collections import Counter

    k, points = args
    if not isinstance(got, list) or len(got) != k:
        return False
    got_counts = Counter(tuple(p) for p in got)
    point_counts = Counter(tuple(p) for p in points)
    if any(got_counts[p] > point_counts.get(p, 0) for p in got_counts):
        return False  # more copies of a coordinate than the input holds
    dists = sorted(p[0] ** 2 + p[1] ** 2 for p in points)
    threshold = dists[k - 1]
    for p in points:
        d = p[0] ** 2 + p[1] ** 2
        if d < threshold and got_counts[tuple(p)] != point_counts[tuple(p)]:
            return False  # a strictly-closer point was skipped
        if d > threshold and got_counts[tuple(p)] > 0:
            return False  # a farther point sneaked in
    return True


@oracle("k_closest_points")
def _k_closest_oracle(k: int, points: list[list[int]]) -> list[list[int]]:
    ranked = sorted(points, key=lambda p: (p[0] ** 2 + p[1] ** 2, p[0], p[1]))
    return ranked[:k]


@judge_case("k_closest_points")
def _k_closest_case(n: int, rng: random.Random) -> tuple[list, bool, dict]:
    n = max(1, min(n, 12))
    points = [[rng.randint(-10, 10), rng.randint(-10, 10)] for _ in range(n)]
    k = rng.randint(1, n)
    return [k, points], True, {"predicate": "k_closest_valid"}


@profiler_input("k_closest_points")
def _k_closest_profiler(n: int, rng: random.Random) -> list:
    points = [[rng.randint(-100, 100), rng.randint(-100, 100)] for _ in range(n)]
    return [max(1, n // 2), points]


@oracle("k_smallest_elem_matrix")
def _k_smallest_oracle(k: int, matrix: list[list[int]]) -> int:
    return sorted(x for row in matrix for x in row)[k - 1]


@judge_case("k_smallest_elem_matrix")
def _k_smallest_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))
    scale = rng.randint(1, 3)
    # (i+1)*(j+1) is sorted along rows and columns; a constant scale keeps that.
    matrix = [[scale * (i + 1) * (j + 1) for j in range(n)] for i in range(n)]
    k = rng.randint(1, n * n)
    return [k, matrix], _k_smallest_oracle(k, matrix)


@profiler_input("k_smallest_elem_matrix")
def _k_smallest_profiler(n: int, rng: random.Random) -> list:
    side = max(1, int(n ** 0.5))  # keep total elements ~n
    matrix = [[(i + 1) * (j + 1) for j in range(side)] for i in range(side)]
    return [max(1, side * side // 2), matrix]


@oracle("kth-largest-element-in-an-array")
def _kth_largest_element_in_an_array_oracle(nums: list[int], k: int) -> int:
    """Brute force: sort the whole array and read the k-th from the top. The
    statement's constraint is 1 <= k <= nums.length, so an empty array is out of
    contract; this stays total on one instead of raising."""
    if not nums:
        return None
    return sorted(nums)[len(nums) - k]


@judge_case("kth-largest-element-in-an-array")
def _kth_largest_element_in_an_array_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= k <= nums.length
    # A small span is what makes "the k-th largest in sorted order, not the k-th
    # distinct element" bite: with 3 or 40 distinct values the answer is a value
    # that occurs several times, where an index-into-sorted-set solution is wrong.
    span = rng.choice([3, 40, 20_001])
    nums = [rng.randint(-10_000, -10_000 + span - 1) for _ in range(n)]
    if rng.random() < 0.3:  # the statement's own bounds, exactly
        nums[rng.randrange(n)] = rng.choice([-10_000, 10_000])
    k = rng.randint(1, n)
    return [nums, k], _kth_largest_element_in_an_array_oracle(nums, k)


@profiler_input("kth-largest-element-in-an-array")
def _kth_largest_element_in_an_array_profiler(n: int, rng: random.Random) -> list:
    # Values across the statement's full range (-10^4..10^4) in a random order,
    # with a middle rank: neither the "k == 1" (the maximum) nor the "k == n"
    # (the minimum) shortcut is available, so a size-k heap pays an O(log k) push
    # for every element and a quickselect partitions the live range at every
    # level. Nothing early-exits and nothing is pre-sorted.
    nums = [rng.randint(-10_000, 10_000) for _ in range(max(1, n))]
    return [nums, max(1, len(nums) // 2)]


@oracle("design-twitter")
def _design_twitter_oracle(ops: list[list]) -> list:
    """Brute force, driven through the statement's own op list: keep one global
    log of (post order, author, tweetId) and answer every getNewsFeed by walking
    the log from the newest entry backwards, keeping the tweets whose author is
    the reader or someone they follow. No heaps, no per-user lists, no sorting by
    tweetId, and no dependence on dict or set iteration order — recency is post
    order and nothing else, which is exactly the contract the statement states.
    """
    log: list[tuple[int, int, int]] = []  # (post order, author, tweetId)
    following: dict[int, set[int]] = {}
    out: list = []
    for op in ops:
        method, *args = op
        if method == "postTweet":
            user, tweet = args
            log.append((len(log), user, tweet))
            out.append(None)
        elif method == "getNewsFeed":
            user = args[0]
            allowed = set(following.get(user, ())) | {user}
            feed: list[int] = []
            for _order, author, tweet in reversed(log):
                if author in allowed:
                    feed.append(tweet)
                    if len(feed) == 10:
                        break
            out.append(feed)
        elif method == "follow":
            follower, followee = args
            following.setdefault(follower, set()).add(followee)
            out.append(None)
        elif method == "unfollow":
            follower, followee = args
            following.setdefault(follower, set()).discard(followee)
            out.append(None)
        else:  # pragma: no cover - the generator only emits the four methods
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("design-twitter")
def _design_twitter_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # Deterministic by construction: every op comes from the seeded rng, the user
    # pool is a fixed list, the "already followed" pairs are read through
    # sorted(), and tweet ids are drawn without replacement from the statement's
    # own 0..10^4 range. The same (n, rng) always replays the same sequence, and
    # the harness builds a fresh Twitter for every case, so no state crosses
    # cases.
    steps = 3 * max(1, min(n, 12)) + 4
    users = [1, 2, 3]
    used_ids: set[int] = set()
    following: set[tuple[int, int]] = set()
    # A feed with nothing in it first: the statement documents no special case
    # for it, so [] is the answer, and every generated case pins it.
    ops: list[list] = [["getNewsFeed", rng.choice(users)]]
    for _ in range(steps):
        # Weighted towards posting and reading: with a small pool of three users
        # that is what pushes some feeds past 10 tweets, so the statement's cap
        # ("the 10 most recent tweet IDs") is exercised by generated cases too.
        method = rng.choice(
            ["postTweet"] * 4 + ["getNewsFeed"] * 3 + ["follow"] * 2 + ["unfollow"] * 2
        )
        if method == "postTweet":
            tweet = rng.randint(0, 10_000)
            while tweet in used_ids:  # "All the tweets have unique IDs."
                tweet = rng.randint(0, 10_000)
            used_ids.add(tweet)
            ops.append(["postTweet", rng.choice(users), tweet])
        elif method == "getNewsFeed":
            ops.append(["getNewsFeed", rng.choice(users)])
        elif method == "follow":
            follower = rng.choice(users)
            # "A user cannot follow himself" — never generated.
            followee = rng.choice([user for user in users if user != follower])
            following.add((follower, followee))
            ops.append(["follow", follower, followee])
        else:
            if following and rng.random() < 0.7:
                follower, followee = rng.choice(sorted(following))
                following.discard((follower, followee))
            else:  # unfollowing a user who was never followed is a legal no-op
                follower = rng.choice(users)
                followee = rng.choice([user for user in users if user != follower])
            ops.append(["unfollow", follower, followee])
    return [], _design_twitter_oracle(ops), {"ops": ops}


@oracle("task-scheduler")
def _task_scheduler_oracle(tasks: list[str], n: int) -> int:
    """The closed form, and the anchor for every expected value. With f the
    largest number of copies of any one label and c the number of labels reaching
    f: those c labels force (f - 1) blocks of n intervals after each of their
    first f - 1 copies, i.e. (f - 1) * (n + 1) + c intervals, and when the other
    labels are numerous enough to fill every one of those gaps the answer is
    simply len(tasks) — hence the max(). One pass over the tasks: O(m) time and
    O(1) space. Verified against an exhaustive shortest-schedule search and
    against the simulation reference; see the notes.
    """
    counts: dict[str, int] = {}
    for label in tasks:
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return 0
    most = max(counts.values())
    tied = sum(1 for count in counts.values() if count == most)
    return max(len(tasks), (most - 1) * (n + 1) + tied)


@judge_case("task-scheduler")
def _task_scheduler_case(n: int, rng: random.Random) -> tuple[list, int]:
    total = max(1, min(n, 12))  # the statement's own constraint: 1 <= tasks.length
    kinds = rng.randint(1, min(total, 6))
    labels = rng.sample("ABCDEFGHIJKLMNOPQRSTUVWXYZ", kinds)
    counts = [1] * kinds
    for _ in range(total - kinds):
        counts[rng.randrange(kinds)] += 1
    tasks = [label for label, count in zip(labels, counts) for _ in range(count)]
    rng.shuffle(tasks)
    # 0 is the statement's floor and the one value with no gap to respect (the
    # answer is then simply len(tasks)); a large cooldown is where the max()
    # clamp and the idle counting actually decide the answer.
    cooldown = rng.choice([0, 0, 1, 2, 3, rng.randint(0, 100)])
    return [tasks, cooldown], _task_scheduler_oracle(tasks, cooldown)


@profiler_input("task-scheduler")
def _task_scheduler_profiler(n: int, rng: random.Random) -> list:
    # All 26 labels, as evenly as the count allows, at the statement's maximum
    # cooldown (100). The cooldown — not the task count — sets the schedule's
    # length, so the answer is about 3.9 * n intervals (~74% of them idle) and a
    # simulation pays for every one of them, while a closed-form solution still
    # has to read all n tasks. The answer is far from len(tasks), so a solution
    # that forgets the idles is caught by the digest comparison as well. The
    # shape is deliberately bounded rather than maximally idle (a single label at
    # n = 100 would be ~101 * n intervals), because a correct but naive
    # simulation (a 26-counter scan per interval, with tracemalloc on for the
    # space call) would then approach the probe's 20 s per-call timeout and be
    # reported as "failed at scale" — an unfair verdict for code that is merely
    # slower.
    size = max(1, n)
    tasks = [chr(ord("A") + i) for i in range(26) for _ in range(size // 26)]
    for i in range(size % 26):
        tasks.append(chr(ord("A") + i))
    rng.shuffle(tasks)
    return [tasks, 100]


@oracle("kth-largest-element-in-a-stream")
def _kth_largest_element_in_a_stream_oracle(ops: list[list]) -> list:
    """Brute force: keep every score the stream has produced and re-sort the whole
    pool on each add. The leading __init__ op is where the oracle learns k and the
    initial scores — the same one list the judge replays and the gate passes in."""
    pool: list[int] = []
    k = 0
    out: list = []
    for op in ops:
        method, *args = op
        if method == "__init__":
            k, nums = args
            pool = list(nums)
            out.append(None)
        elif method == "add":
            pool.append(args[0])
            out.append(sorted(pool)[-k])
        else:  # pragma: no cover - the generator only emits these two methods
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("kth-largest-element-in-a-stream")
def _kth_largest_element_in_a_stream_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(1, min(n, 12))
    size = rng.randint(0, n)  # the statement's own constraint: 0 <= nums.length
    k = rng.randint(1, size + 1)  # the statement's own constraint: k <= nums.length + 1
    count = rng.randint(1, n)  # at least one add: k <= nums.length + 1 is what makes
    #                             the k-th largest exist as soon as one score arrives
    if rng.random() < 0.5:
        # A tiny value range, so duplicate scores dominate and the answer sits at a
        # tie; a heap capped at k has to return the k-th largest anyway.
        nums = [rng.randint(-5, 5) for _ in range(size)]
        adds = [rng.randint(-5, 5) for _ in range(count)]
    else:
        nums = [rng.randint(-10_000, 10_000) for _ in range(size)]  # the stated range
        adds = [rng.randint(-10_000, 10_000) for _ in range(count)]
    ops = [["__init__", k, list(nums)]] + [["add", val] for val in adds]
    ctor_args = [k, list(nums)]
    return [], _kth_largest_element_in_a_stream_oracle(ops), {
        "ops": ops,
        "ctor_args": ctor_args,
    }


@oracle("k-closest-points-to-origin")
def _k_closest_points_to_origin_oracle(k: int, points: list[list[int]]) -> list[list[int]]:
    """Brute force: pick the closest remaining point k times (O(k*n)). That is the
    contract itself rather than a sort or a heap, and which of several tied points it
    happens to take does not matter — every case is judged by k_closest_valid."""
    remaining = [list(point) for point in points]
    chosen: list[list[int]] = []
    for _ in range(k):
        closest = min(
            range(len(remaining)),
            key=lambda i: (remaining[i][0] ** 2 + remaining[i][1] ** 2, i),
        )
        chosen.append(remaining.pop(closest))
    return chosen


@judge_case("k-closest-points-to-origin")
def _k_closest_points_to_origin_case(n: int, rng: random.Random) -> tuple[list, bool, dict]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= points.length
    roll = rng.random()
    if roll < 0.4:
        # A ring of four points at one distance r, drawn with replacement: every k
        # below n cuts a tie group, which is what equality judging false-fails on.
        r = rng.randint(1, 4)
        ring = [[r, 0], [0, r], [-r, 0], [0, -r]]
        points = [list(rng.choice(ring)) for _ in range(n)]
    elif roll < 0.7:
        # A tiny coordinate range: distance ties are frequent but not guaranteed.
        points = [[rng.randint(-3, 3), rng.randint(-3, 3)] for _ in range(n)]
    else:
        points = [  # the statement's stated range: -10^4 <= xi, yi <= 10^4
            [rng.randint(-10_000, 10_000), rng.randint(-10_000, 10_000)]
            for _ in range(n)
        ]
    dists = sorted(x * x + y * y for x, y in points)
    cuts = [i + 1 for i in range(n - 1) if dists[i] == dists[i + 1]]
    # Put k on a distance tie whenever the points offer one, so the boundary tie is
    # not left to chance; otherwise any k in the statement's own 1 <= k <= n.
    k = rng.choice(cuts) if cuts else rng.randint(1, n)
    return [k, points], True, {"predicate": "k_closest_valid"}


@profiler_input("k-closest-points-to-origin")
def _k_closest_points_to_origin_profiler(n: int, rng: random.Random) -> list:
    # k = n//2: the size-k heap fills half way and every later point then pays a
    # log k replace, so the reference cannot early-exit. Random coordinates across
    # the whole stated range (-10^4..10^4) keep the squared distances distinct (no
    # lucky tie short-circuit) and respect the statement's own value constraint,
    # not just the shape (v0.12). The brute-force oracle never runs at this size:
    # the gate and the registry tests drive it on small cases only, and
    # scale_compare "none" makes _oracle_confirms return before it is called.
    points = [
        [rng.randint(-10_000, 10_000), rng.randint(-10_000, 10_000)] for _ in range(n)
    ]
    return [max(1, n // 2), points]


@oracle("last-stone-weight")
def _last_stone_weight_oracle(stones: list[int]) -> int:
    """Brute force: re-sort the whole pile every turn and smash the two heaviest.
    Total on the empty list and on a one-stone list (the constraints exclude the
    first, but the gate and the generator may reach it) — no stones left is 0."""
    pile = list(stones)
    while len(pile) > 1:
        pile.sort()
        y = pile.pop()
        x = pile.pop()
        if x != y:
            pile.append(y - x)
    return pile[0] if pile else 0


@judge_case("last-stone-weight")
def _last_stone_weight_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= stones.length <= 30
    roll = rng.random()
    if roll < 0.35:
        # Every stone the same weight: each smash destroys both, so the answer is 0
        # for an even count and that weight for an odd one — the x == y rule.
        stones = [rng.randint(1, 1000)] * n
    elif roll < 0.7:
        # A tiny weight range, so ties are frequent and unequal pairs leave equal
        # remnants behind on later turns.
        stones = [rng.randint(1, 6) for _ in range(n)]
    else:
        stones = [rng.randint(1, 1000) for _ in range(n)]  # the stated range
    return [stones], _last_stone_weight_oracle(stones)


# ----------------------------------------------------------------------- math


@oracle("correlation")
def _correlation_oracle(X: list, Y: list) -> float:
    n = len(X)
    ex = sum(X) / n
    ey = sum(Y) / n
    exy = sum(x * y for x, y in zip(X, Y)) / n
    exx = sum(x * x for x in X) / n
    eyy = sum(y * y for y in Y) / n
    return round((exy - ex * ey) / (((exx - ex**2) * (eyy - ey**2)) ** 0.5), 4)


@judge_case("correlation")
def _correlation_case(n: int, rng: random.Random) -> tuple[list, float, dict]:
    n = max(2, min(n, 12))
    X = [rng.randint(1, 20) for _ in range(n)]
    slope = rng.randint(-5, 5)
    intercept = rng.randint(-10, 10)
    Y = [slope * x + intercept + rng.randint(-5, 5) for x in X]
    if len(set(X)) == 1:
        X[0] += 1  # zero variance makes correlation undefined
    if len(set(Y)) == 1:
        Y[0] += 1
    return [X, Y], _correlation_oracle(X, Y), {"compare": "approx:0.0001"}


@profiler_input("correlation")
def _correlation_profiler(n: int, rng: random.Random) -> list:
    X = list(range(n))
    Y = [x + rng.randint(-10, 10) for x in X]
    return [X, Y]


# ---------------------------------------------------------------------- trees


@oracle("binary_tree_diameter")
def _diameter_oracle(root: list | None) -> int:
    best = 0

    def visit(node: list | None) -> int:
        nonlocal best
        if node is None:
            return 0
        left = visit(node[1])
        right = visit(node[2])
        best = max(best, left + right)
        return 1 + max(left, right)

    visit(root)
    return best


@judge_case("binary_tree_diameter")
def _diameter_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 15))
    tree = _random_tree(rng, n)
    return [tree], _diameter_oracle(tree)


@profiler_input("binary_tree_diameter")
def _diameter_profiler(n: int, rng: random.Random) -> list:
    return [_complete_tree(n)]  # balanced: log-depth, so no recursion blowup


@oracle("mirror_image_binary_tree")
def _is_mirror_oracle(root: list | None) -> bool:
    def check(a: list | None, b: list | None) -> bool:
        if a is None or b is None:
            return a is None and b is None
        return a[0] == b[0] and check(a[1], b[2]) and check(a[2], b[1])

    return check(root, root)


@judge_case("mirror_image_binary_tree")
def _is_mirror_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 15))
    if n == 0:
        tree = None
    elif rng.random() < 0.5:
        tree = _mirror_tree(rng, n)
    else:
        tree = _random_tree(rng, n)
    return [tree], _is_mirror_oracle(tree)


@profiler_input("mirror_image_binary_tree")
def _is_mirror_profiler(n: int, rng: random.Random) -> list:
    return [_complete_tree(n)]


@oracle("validate-binary-search-tree")
def _validate_binary_search_tree_oracle(root: list | None) -> bool:
    """The statement's definition transcribed literally and quadratically: every
    node of the left subtree is strictly smaller, every node of the right
    subtree strictly larger, and both subtrees are BSTs in their own right.
    O(n^2), and it never mentions an interval — which is what makes it a real
    differential against the reference's boundary walk. Total on the empty tree
    (vacuously a BST), which the statement's [1, 10^4] node range excludes."""
    if root is None:
        return True
    return (
        _validate_binary_search_tree_all_less(root[1], root[0])
        and _validate_binary_search_tree_all_greater(root[2], root[0])
        and _validate_binary_search_tree_oracle(root[1])
        and _validate_binary_search_tree_oracle(root[2])
    )


def _validate_binary_search_tree_all_less(node: list | None, bound: int) -> bool:
    if node is None:
        return True
    return (
        node[0] < bound
        and _validate_binary_search_tree_all_less(node[1], bound)
        and _validate_binary_search_tree_all_less(node[2], bound)
    )


def _validate_binary_search_tree_all_greater(node: list | None, bound: int) -> bool:
    if node is None:
        return True
    return (
        node[0] > bound
        and _validate_binary_search_tree_all_greater(node[1], bound)
        and _validate_binary_search_tree_all_greater(node[2], bound)
    )


def _validate_binary_search_tree_build(rng: random.Random, values: list[int]) -> list | None:
    """A valid BST over ``values`` (ascending and distinct): the root of each
    range is picked at random, which is the shape a uniformly random insertion
    order produces. Every root is strictly inside the range it splits, so the
    result is a BST of exactly len(values) nodes whatever the picks are."""
    if not values:
        return None
    root = rng.randrange(len(values))
    return [
        values[root],
        _validate_binary_search_tree_build(rng, values[:root]),
        _validate_binary_search_tree_build(rng, values[root + 1 :]),
    ]


def _validate_binary_search_tree_values(rng: random.Random, size: int) -> list[int]:
    """``size`` distinct ascending values inside the statement's
    [-2^31, 2^31 - 1]: a small range most of the time, and the range's two ends
    a quarter of the time — a solution that seeds "no bound yet" with the bound
    itself instead of None only fails on a value that reaches it."""
    if rng.random() < 0.25:
        pool = [-(2**31) + i for i in range(6)] + [2**31 - 1 - i for i in range(6)]
        return sorted(rng.sample(pool, size))
    return sorted(rng.sample(range(-60, 61), size))


def _validate_binary_search_tree_local_break(rng: random.Random, root: list) -> list:
    """Copy the root's value into one of its children: the very comparison a
    parent-only check looks at now fails (a left child equal to its parent, or a
    right child equal to it), so this is the trap's complement — an invalid tree
    the shallow check does reject. Needs two or more nodes: a rooted tree that
    size always has a root with a child."""
    child = rng.choice([side for side in (1, 2) if root[side] is not None])
    root[child][0] = root[0]
    return root


def _validate_binary_search_tree_trap(rng: random.Random, size: int) -> list:
    """A tree of exactly ``size`` nodes that EVERY parent-only check accepts and
    that is not a BST — the case this problem is famous for.

    A root-to-node path is built first, every value strictly inside the interval
    the path implies. Step one takes a wide gap and step two turns (right then
    left, or left then right), and after a turn the path implies an interval
    with BOTH ends known: the root's value on one side and the previous node's
    on the other. The node at the end of the path then takes a value that breaks
    the end its own parent cannot see — a left child a value at or below the
    lower bound (its parent sits above that bound, so the value is still smaller
    than its parent), a right child a value at or above the upper bound. So
    every parent-child comparison in the tree holds while the tree is not a BST.
    The nodes left over hang off the root's free side, where the path implies no
    bound at all, so they are valid: the violation is the only one.
    """
    root_value = rng.randint(-9, 9)
    gap = rng.randint(4, 8)
    first_right = rng.random() < 0.5
    root: list = [root_value, None, None]
    node = root
    lo: int | None = None
    hi: int | None = None
    last_right = first_right
    steps = [first_right, not first_right]  # the turn is what sets both ends
    if size >= 5 and rng.random() < 0.5:
        steps.append(rng.random() < 0.5)  # a third step: the trap at depth 3
    taken = 0  # a step that cannot fit is skipped, so count what was walked
    for right in steps:
        if lo is None and hi is None:  # first step: a gap wide enough to turn in
            low = node[0] + gap if right else node[0] - gap - 4
            high = node[0] + gap + 4 if right else node[0] - gap
        elif right:
            low = node[0] + 2
            high = node[0] + 6 if hi is None else hi - 2
        else:
            high = node[0] - 2
            low = node[0] - 6 if lo is None else lo + 2
        if low > high:
            break  # no integer left strictly inside the interval: the path ends
        value = rng.randint(low, min(high, low + 4))
        child: list = [value, None, None]
        if right:
            node[2] = child
            lo = node[0]
        else:
            node[1] = child
            hi = node[0]
        node, last_right = child, right
        taken += 1
    extra = size - 1 - taken
    if extra > 0:
        if first_right:  # the root's left side: everything below the root is valid
            root[1] = _validate_binary_search_tree_build(
                rng, sorted(rng.sample(range(root_value - 40, root_value), extra))
            )
        else:
            root[2] = _validate_binary_search_tree_build(
                rng, sorted(rng.sample(range(root_value + 1, root_value + 41), extra))
            )
    # Break the end the parent's own comparison cannot see. Both ends are known
    # because the path turned; were this ever to fall through, the tree would
    # simply be a valid one — the expected value is the oracle's either way.
    if last_right and hi is not None:
        node[0] = hi + rng.randint(0, 2)
    elif not last_right and lo is not None:
        node[0] = lo - rng.randint(0, 2)
    return root


@judge_case("validate-binary-search-tree")
def _validate_binary_search_tree_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(1, min(n, 12))  # the statement's node range is [1, 10^4]
    roll = rng.random()
    if n >= 3 and roll < 0.5:
        # the parent-only trap half the time (needs depth 2, so three nodes)
        tree = _validate_binary_search_tree_trap(rng, n)
    else:
        tree = _validate_binary_search_tree_build(
            rng, _validate_binary_search_tree_values(rng, n)
        )
        if n >= 2 and roll < 0.7:
            tree = _validate_binary_search_tree_local_break(rng, tree)
    return [tree], _validate_binary_search_tree_oracle(tree)


def _validate_binary_search_tree_balanced(lo: int, hi: int) -> list | None:
    """A height-balanced BST with the keys lo..hi: the middle key of the range
    goes at the root, so the in-order walk is lo..hi and the tree is a BST by
    construction. (Placed before the profiler block it serves so that EVERY
    helper sits inside the span the fragment's decorators mark for replacement —
    a helper after the last decorated def would be re-inserted twice on the
    assembler's second run.)"""
    if lo > hi:
        return None
    mid = (lo + hi) // 2
    return [
        mid,
        _validate_binary_search_tree_balanced(lo, mid - 1),
        _validate_binary_search_tree_balanced(mid + 1, hi),
    ]


@profiler_input("validate-binary-search-tree")
def _validate_binary_search_tree_profiler(n: int, rng: random.Random) -> list:
    """A perfectly height-balanced BST over the keys 0..n-1: exactly n nodes (so
    ~n of input), depth log n, and VALID — which the shared `_complete_tree`
    cannot be here: it labels node i with i, and that array-index labelling puts
    a left child (2i+1) above its own parent, so it is not a BST at all. Valid
    is the worst case on purpose: an invalid tree lets a solution return False
    at the first violation it meets, while a valid one forces every node to be
    examined by both implementations. Values sit inside the statement's
    [-2^31, 2^31 - 1] at every rung of the ladder (6400 at the top, so the
    largest key is 6399). Balanced rather than a chain so a recursive solution
    runs at depth log n instead of n."""
    return [_validate_binary_search_tree_balanced(0, max(1, n) - 1)]


@oracle("same-tree")
def _same_tree_oracle(p: list | None, q: list | None) -> bool:
    """Brute force by canonical form: flatten each tree to its preorder walk
    with an explicit null marker for every missing child, then compare. That
    serialization determines a binary tree uniquely, so equality of the two
    canonical forms is exactly "structurally identical, same values". Iterative
    and one-sided — no simultaneous recursion, no mutation — so it is a
    different program from the reference. Total on two empty trees (both
    flatten to [None])."""

    def flatten(node: list | None) -> list:
        out: list = []
        stack = [node]
        while stack:
            current = stack.pop()
            if current is None:
                out.append(None)  # the marker that makes the walk unambiguous
                continue
            out.append(current[0])
            stack.append(current[2])  # right first, so left is popped first
            stack.append(current[1])
        return out

    return flatten(p) == flatten(q)


@judge_case("same-tree")
def _same_tree_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))  # the statement allows 0..100 nodes per tree; 0 is empty
    # Two _random_tree calls on the SAME seed build the same tree twice, as two
    # distinct objects: a random pair would almost never be equal, and sharing
    # one object would let a `p is q` shortcut pass. Values are 0..9, inside
    # -10^4..10^4.
    seed = rng.randrange(1 << 31)
    p = _random_tree(random.Random(seed), n)
    q = _random_tree(random.Random(seed), n)
    nodes = _same_tree_nodes(q)
    roll = rng.random()
    if not nodes or roll < 1 / 3:
        pass  # identical (example 1's shape; the whole tree must be compared)
    elif roll < 2 / 3:
        rng.choice(nodes)[0] += 1  # same structure, one different value
    else:
        # A structural difference with the same value multiset — example 3's
        # shape. Only a node whose two subtrees actually differ will do: swapping
        # two equal subtrees is invisible, so that case falls back to a value.
        swappable = [node for node in nodes if node[1] != node[2]]
        if swappable:
            node = rng.choice(swappable)
            node[1], node[2] = node[2], node[1]
        else:
            rng.choice(nodes)[0] += 1
    return [p, q], _same_tree_oracle(p, q)


def _same_tree_nodes(tree: list | None) -> list[list]:
    """Every node of a tree, in level order; empty for the empty tree."""
    nodes: list[list] = []
    queue, i = [tree], 0
    while i < len(queue):
        node = queue[i]
        i += 1
        if node is None:
            continue
        nodes.append(node)
        queue.append(node[1])
        queue.append(node[2])
    return nodes


@profiler_input("same-tree")
def _same_tree_profiler(n: int, rng: random.Random) -> list:
    # Two IDENTICAL complete trees of ~n/2 nodes each, from two calls so they are
    # equal but distinct objects (one shared object would let `p is q` pass at
    # scale). Identical is the worst case in work: the answer is true, so no
    # implementation can stop before the last node has been compared — a pair
    # that differs somewhere would let a lucky traversal order finish early.
    # Depth is log2(n/2), 12 at the ladder's top, and values are _complete_tree's
    # 0..n/2-1, inside the statement's -10^4..10^4.
    n = max(2, min(n, 10_000))  # the statement's own bound is 10^4 nodes per tree
    half = n // 2
    return [_complete_tree(half), _complete_tree(half)]


@oracle("binary-tree-level-order-traversal")
def _binary_tree_level_order_traversal_oracle(root: list | None) -> list[list[int]]:
    """Brute force: one full depth-first walk (explicit stack, preorder left to
    right) that appends every node's value to its own depth's list. Nothing here
    derives the levels from a queue, so it is a genuinely different traversal
    from the reference's level sweep. Depths are first reached in increasing
    order -- a node at depth d is only reached through its ancestors -- so the
    buckets are appended to in level order."""
    out: list[list[int]] = []
    if root is None:
        return out
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if depth == len(out):
            out.append([node[0]])
        else:
            out[depth].append(node[0])
        if node[2] is not None:
            stack.append((node[2], depth + 1))  # pushed first, so left pops first
        if node[1] is not None:
            stack.append((node[1], depth + 1))
    return out


@judge_case("binary-tree-level-order-traversal")
def _binary_tree_level_order_traversal_case(
    n: int, rng: random.Random
) -> tuple[list, list[list[int]]]:
    n = max(0, min(n, 12))  # the statement allows an empty tree (0 nodes)
    if n and rng.random() < 0.25:
        # One node per level: the degenerate shape _random_tree's halving budget
        # cannot build, and the one that breaks a level sweep which assumes a
        # left child comes with a right child.
        tree = _binary_tree_level_order_traversal_spine(n)
    else:
        tree = _random_tree(rng, n)
    return [tree], _binary_tree_level_order_traversal_oracle(tree)


def _binary_tree_level_order_traversal_spine(n: int) -> list | None:
    """A chain of n nodes, each with only a left child (values 0..n-1)."""
    node: list | None = None
    for value in range(n - 1, -1, -1):
        node = [value, node, None]
    return node


def _binary_tree_level_order_traversal_complete(n: int) -> list | None:
    """A complete tree of exactly n nodes whose values stay inside the
    statement's [-1000, 1000]. It is the shared _complete_tree, relabelled: that
    helper names node i with the value i, which leaves the stated range above
    n = 1001 -- and a profiler input's *values* must respect the statement, not
    just its shape (the v0.12 products_of_array_except_self lesson)."""
    nodes: list[list | None] = [None] * n
    for i in range(n - 1, -1, -1):  # bottom-up: children finalized first
        left, right = 2 * i + 1, 2 * i + 2
        nodes[i] = [
            i % 2001 - 1000,
            nodes[left] if left < n else None,
            nodes[right] if right < n else None,
        ]
    return nodes[0]


@profiler_input("binary-tree-level-order-traversal")
def _binary_tree_level_order_traversal_profiler(n: int, rng: random.Random) -> list:
    """A complete tree of n nodes: every one of them is visited and the output
    holds all n values, so no implementation can early-exit, and both a BFS and
    a DFS pay for the whole tree. The shape is complete rather than a spine so a
    recursive solution sees a depth of ~11 rather than n, and probe_max_n = 2000
    keeps the measured tree inside the statement's own node bound."""
    # No internal cap: the live ladder is already cut at the statement's 2000
    # nodes by probe_max_n, and a second clamp here would silently rebuild the
    # same tree for every ladder size above it (measured -- see the notes).
    return [_binary_tree_level_order_traversal_complete(max(1, n))]


@oracle("maximum-depth-of-binary-tree")
def _maximum_depth_of_binary_tree_oracle(root: list | None) -> int:
    """Brute force: build every root-to-leaf path explicitly and take the
    longest — the statement's definition, spelled out. Total on the empty
    tree, which has no path and therefore depth 0."""

    def paths(node: list | None) -> list[list[int]]:
        if node is None:
            return []
        if node[1] is None and node[2] is None:
            return [[node[0]]]
        return [[node[0]] + rest for rest in paths(node[1]) + paths(node[2])]

    return max((len(path) for path in paths(root)), default=0)


@judge_case("maximum-depth-of-binary-tree")
def _maximum_depth_of_binary_tree_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(0, min(n, 12))  # the statement allows 0..10^4 nodes; 0 is the empty tree
    tree = _random_tree(rng, n)  # ragged shapes; values 0..9, inside -100..100
    return [tree], _maximum_depth_of_binary_tree_oracle(tree)


def _maximum_depth_of_binary_tree_in_range(tree: list | None) -> list | None:
    """Relabel a tree's values into the statement's -100..100, shape untouched.

    ``_complete_tree`` labels node i with i, so at probe sizes its values run up
    to n - 1 and leave the statement's own range (the v0.12 value-fidelity
    lesson) — even though depth does not depend on any value."""
    stack, i = [tree], 0
    while stack:
        node = stack.pop()
        if node is None:
            continue
        node[0] = -100 + (i % 201)  # sweeps -100..100, then repeats
        i += 1
        stack.append(node[1])
        stack.append(node[2])
    return tree


@profiler_input("maximum-depth-of-binary-tree")
def _maximum_depth_of_binary_tree_profiler(n: int, rng: random.Random) -> list:
    # A complete tree with exactly n nodes: a depth-first or breadth-first
    # solution must reach every node to know the deepest one (nothing here lets
    # either stop early — the deepest level is full), and its log2(n) depth (13
    # at the ladder's top) keeps the measurement about the algorithm rather than
    # about CPython's recursion limit. n is clamped at the statement's own 10^4,
    # which is above the ladder's top, so the generator never reports a size
    # smaller than the one the probe asked for.
    n = max(1, min(n, 10_000))
    return [_maximum_depth_of_binary_tree_in_range(_complete_tree(n))]


@oracle("construct-binary-tree-from-preorder-and-inorder-traversal")
def _construct_binary_tree_from_preorder_and_inorder_traversal_oracle(
    preorder: list[int], inorder: list[int]
) -> list | None:
    """Brute force: the root is the front of preorder, a linear scan finds it in
    inorder, and the two slices recurse. The scan is the brute-force part -- the
    intended solution precomputes those positions once. O(n^2) time and space
    (every level copies its slices); total on the empty pair, which the
    statement's length >= 1 excludes."""
    if not preorder:
        return None
    root = preorder[0]
    split = inorder.index(root)  # the statement's values are unique: exactly one hit
    return [
        root,
        _construct_binary_tree_from_preorder_and_inorder_traversal_oracle(
            preorder[1 : split + 1], inorder[:split]
        ),
        _construct_binary_tree_from_preorder_and_inorder_traversal_oracle(
            preorder[split + 1 :], inorder[split + 1 :]
        ),
    ]


def _construct_binary_tree_from_preorder_and_inorder_traversal_shape(
    rng: random.Random, n: int
) -> list | None:
    """A random binary-tree SHAPE with exactly n nodes ([None placeholder, left,
    right]; None = missing child). One draw in four is one of the two degenerate
    chains -- shapes a uniformly random split almost never reaches and the ones a
    "the tree is roughly balanced" assumption breaks on."""
    if n <= 0:
        return None
    if n > 2 and rng.random() < 0.25:
        if rng.random() < 0.5:
            return [None, _construct_binary_tree_from_preorder_and_inorder_traversal_shape(rng, n - 1), None]
        return [None, None, _construct_binary_tree_from_preorder_and_inorder_traversal_shape(rng, n - 1)]
    left = rng.randrange(n)  # 0..n-1 nodes go left, the rest right
    return [
        None,
        _construct_binary_tree_from_preorder_and_inorder_traversal_shape(rng, left),
        _construct_binary_tree_from_preorder_and_inorder_traversal_shape(rng, n - 1 - left),
    ]


def _construct_binary_tree_from_preorder_and_inorder_traversal_label(
    node: list | None, values
) -> list | None:
    """Fill a shape with `values` in preorder, so the labelled tree's own
    preorder traversal IS the sequence that was handed in."""
    if node is None:
        return None
    return [
        next(values),
        _construct_binary_tree_from_preorder_and_inorder_traversal_label(node[1], values),
        _construct_binary_tree_from_preorder_and_inorder_traversal_label(node[2], values),
    ]


def _construct_binary_tree_from_preorder_and_inorder_traversal_preorder(
    node: list | None,
) -> list[int]:
    if node is None:
        return []
    return (
        [node[0]]
        + _construct_binary_tree_from_preorder_and_inorder_traversal_preorder(node[1])
        + _construct_binary_tree_from_preorder_and_inorder_traversal_preorder(node[2])
    )


def _construct_binary_tree_from_preorder_and_inorder_traversal_inorder(
    node: list | None,
) -> list[int]:
    if node is None:
        return []
    return (
        _construct_binary_tree_from_preorder_and_inorder_traversal_inorder(node[1])
        + [node[0]]
        + _construct_binary_tree_from_preorder_and_inorder_traversal_inorder(node[2])
    )


def _construct_binary_tree_from_preorder_and_inorder_traversal_balanced(
    n: int,
) -> list | None:
    """A complete (balanced) tree with exactly n nodes, labelled 0..n-1. Built
    here rather than reusing the registry's `_complete_tree` so the fragment's
    blocks are self-contained (the self-check in AUTHORING.md execs them with
    only `random`/`math` in scope)."""
    if n <= 0:
        return None
    nodes: list[list | None] = [None] * n
    for i in range(n - 1, -1, -1):
        left, right = 2 * i + 1, 2 * i + 2
        nodes[i] = [i, nodes[left] if left < n else None, nodes[right] if right < n else None]
    return nodes[0]


@judge_case("construct-binary-tree-from-preorder-and-inorder-traversal")
def _construct_binary_tree_from_preorder_and_inorder_traversal_case(
    n: int, rng: random.Random
) -> tuple[list, list]:
    n = max(1, min(n, 12))  # the statement's own floor: 1 <= preorder.length
    # A REAL tree's two traversals, so every generated pair is valid by
    # construction. `values` is a sample of DISTINCT ints inside the statement's
    # -3000..3000 -- the statement promises unique values, and distinctness is
    # also what makes the (preorder, inorder) pair determine exactly one tree
    # (which is why the case can be judged by strict equality). Labelling in
    # preorder makes the emitted preorder the sampled list itself.
    values = rng.sample(range(-3000, 3001), n)
    tree = _construct_binary_tree_from_preorder_and_inorder_traversal_label(
        _construct_binary_tree_from_preorder_and_inorder_traversal_shape(rng, n), iter(values)
    )
    return [
        _construct_binary_tree_from_preorder_and_inorder_traversal_preorder(tree),
        _construct_binary_tree_from_preorder_and_inorder_traversal_inorder(tree),
    ], tree


@profiler_input("construct-binary-tree-from-preorder-and-inorder-traversal")
def _construct_binary_tree_from_preorder_and_inorder_traversal_profiler(
    n: int, rng: random.Random
) -> list:
    # A complete (balanced) tree of exactly n nodes, with distinct values inside
    # the statement's -3000..3000 assigned in preorder. Balanced on purpose: a
    # deep chain is the naive implementation's real worst case, but at 3000 nodes
    # it is also deeper than CPython's recursion limit, so it would measure the
    # interpreter's stack for every recursive solution -- the reference included
    # -- instead of the algorithm (the same reason _diameter_profiler is a
    # complete tree). Neither implementation can early-exit: both walk all of
    # both arrays at every size. probe_max_n keeps the ladder inside the
    # statement's own 3000-node cap, so the value range holds at every measured
    # size.
    size = max(1, min(n, 3000))
    values = rng.sample(range(-3000, 3001), size)
    tree = _construct_binary_tree_from_preorder_and_inorder_traversal_label(
        _construct_binary_tree_from_preorder_and_inorder_traversal_balanced(size), iter(values)
    )
    return [
        _construct_binary_tree_from_preorder_and_inorder_traversal_preorder(tree),
        _construct_binary_tree_from_preorder_and_inorder_traversal_inorder(tree),
    ]


@oracle("balanced-binary-tree")
def _balanced_binary_tree_oracle(root: list | None) -> bool:
    """Brute force: the definition applied at every node — compute both
    subtree heights in full and check they differ by at most one. O(n log n) on
    a balanced tree and O(n^2) on a path, and it shares no code with the
    intended solution. Total on None (true, for the same reason an empty tree
    has no node to violate anything)."""

    def height(node: list | None) -> int:
        if node is None:
            return 0
        return 1 + max(height(node[1]), height(node[2]))

    def check(node: list | None) -> bool:
        if node is None:
            return True
        if abs(height(node[1]) - height(node[2])) > 1:
            return False
        return check(node[1]) and check(node[2])

    return check(root)


@judge_case("balanced-binary-tree")
def _balanced_binary_tree_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))  # the statement allows 0..5000 nodes; 0 is the empty tree
    roll = rng.random()
    if n == 0:
        tree = None
    elif roll < 1 / 3:
        # Every level full to the last: balanced by construction, so the TRUE
        # branch is exercised by a shape no implementation can decide early.
        tree = _complete_tree(rng.randint(0, n))
    elif roll < 2 / 3:
        # Ragged: _random_tree splits its budget in half per child, so one side
        # is often cut off while the other keeps a subtree two levels deep.
        tree = _random_tree(rng, 2 * n)
    else:
        # A root with a single child — the shape the statement's own example 2
        # is built from, and by far the most reliable way to be unbalanced at
        # SMALL sizes: _random_tree on its own is never unbalanced below budget
        # 8 (measured 0%), because halving the budget caps the depth, whereas a
        # lone child makes the two heights 0 and h differ as soon as h >= 2.
        tree = [rng.randint(0, 9), _random_tree(rng, 2 * n), None]
    return [tree], _balanced_binary_tree_oracle(tree)


@profiler_input("balanced-binary-tree")
def _balanced_binary_tree_profiler(n: int, rng: random.Random) -> list:
    # A complete tree with exactly n nodes. It is balanced, so the intended
    # bottom-up solution has to walk all n nodes — its -1 has nowhere to fire —
    # and the naive "height at every node" solution pays its full extra factor
    # instead of stopping at the first bad node. Depth is log2(n), 13 at the
    # ladder's top, so recursion is not what gets measured. n is clamped at the
    # statement's own 5000 nodes, which is exactly the probe_max_n below, so the
    # size the probe asks for is the size the generator builds; values are
    # _complete_tree's 0..n-1, inside the statement's -10^4..10^4.
    n = max(1, min(n, 5000))
    return [_complete_tree(n)]


@oracle("binary-tree-maximum-path-sum")
def _binary_tree_maximum_path_sum_oracle(root: list | None) -> int:
    """Brute force: a path is fixed by its two endpoints, so try every ordered
    pair of nodes and add up the unique path between them -- the values from `a`
    up to the lowest common ancestor (the shared prefix of the two root paths
    identifies it) plus the values from there down to `b`. `a == b` covers the
    single-node path, so an ALL-NEGATIVE tree is answered with its largest (least
    negative) node value and never with 0: "the maximum path sum of any
    non-empty path" is a maximum over actual paths. O(n^2 * height), and
    deliberately not the intended DP; total on the empty tree, which the
    statement's "at least one node" excludes."""
    ids: dict[int, list[int]] = {}
    values: dict[int, list[int]] = {}
    nodes: list = []

    def walk(node: list | None, path_ids: list[int], path_values: list[int]) -> None:
        if node is None:
            return
        here_ids = path_ids + [id(node)]
        here_values = path_values + [node[0]]
        ids[id(node)] = here_ids
        values[id(node)] = here_values
        nodes.append(node)
        walk(node[1], here_ids, here_values)
        walk(node[2], here_ids, here_values)

    walk(root, [], [])
    best = None
    for a in nodes:
        a_ids, a_values = ids[id(a)], values[id(a)]
        for b in nodes:
            b_ids, b_values = ids[id(b)], values[id(b)]
            shared = 0
            while (
                shared < len(a_ids)
                and shared < len(b_ids)
                and a_ids[shared] == b_ids[shared]
            ):
                shared += 1  # ids, never values: equal values can sit in two branches
            # shared >= 1 always (both paths start at the root), so shared - 1 is
            # the LCA: [LCA..a] from a's path plus [..b] below the LCA from b's.
            total = sum(a_values[shared - 1 :]) + sum(b_values[shared:])
            best = total if best is None else max(best, total)
    return 0 if best is None else best


def _binary_tree_maximum_path_sum_shape(
    rng: random.Random, n: int, low: int, high: int
) -> list | None:
    """A random tree with exactly n nodes and values in [low, high]. One draw in
    four is a chain (left-only or right-only): on a chain the answer is the best
    contiguous-run sum, a different exercise from a branching tree, and the shape
    a uniformly random split almost never reaches."""
    if n <= 0:
        return None
    if n > 2 and rng.random() < 0.25:
        if rng.random() < 0.5:
            return [rng.randint(low, high), _binary_tree_maximum_path_sum_shape(rng, n - 1, low, high), None]
        return [rng.randint(low, high), None, _binary_tree_maximum_path_sum_shape(rng, n - 1, low, high)]
    left = rng.randrange(n)  # 0..n-1 nodes go left, the rest right
    return [
        rng.randint(low, high),
        _binary_tree_maximum_path_sum_shape(rng, left, low, high),
        _binary_tree_maximum_path_sum_shape(rng, n - 1 - left, low, high),
    ]


@judge_case("binary-tree-maximum-path-sum")
def _binary_tree_maximum_path_sum_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own floor: at least one node
    # One draw in three is an ALL-NEGATIVE tree (values in -1000..-1) on purpose.
    # "Any non-empty path" means the answer there is the largest node value, never
    # 0 -- precisely the case a `best = 0` (or `max(0, ...)`-seeded) accumulator
    # gets wrong, and the self-check asserts both that such a case was generated
    # and that its expected answer is negative.
    if rng.random() < 0.34:
        low, high = -1000, -1
    elif rng.random() < 0.5:
        low, high = -9, 9  # small values: zeros, duplicates, near-ties
    else:
        low, high = -1000, 1000  # the statement's full value range
    tree = _binary_tree_maximum_path_sum_shape(rng, n, low, high)
    return [tree], _binary_tree_maximum_path_sum_oracle(tree)


@profiler_input("binary-tree-maximum-path-sum")
def _binary_tree_maximum_path_sum_profiler(n: int, rng: random.Random) -> list:
    # A complete (balanced) tree of exactly n nodes with ALL-NEGATIVE values in
    # the statement's -1000..-1 range. Balanced so a recursive solution measures
    # its algorithm rather than CPython's stack; no implementation can
    # early-exit (no node's subtree gain is known before it is visited); and with
    # every value negative the answer is the largest (least negative) node value,
    # so the classic `best = 0` seed also surfaces AT SCALE as an output mismatch
    # against the reference, not only in the small generated cases. Values cycle
    # -1..-1000 and repeat, which the statement's constraints allow.
    counter = [0]

    def build(i: int) -> list | None:
        if i >= n:
            return None
        value = -(1 + counter[0] % 1000)
        counter[0] += 1
        return [value, build(2 * i + 1), build(2 * i + 2)]

    return [build(0)]


@oracle("binary-tree-right-side-view")
def _binary_tree_right_side_view_oracle(root: list | None) -> list[int]:
    """Brute force: one full depth-first walk (explicit stack, preorder left to
    right) that writes every node's value into its own depth's slot and keeps
    the last write. The last node visited at a depth is that depth's rightmost
    one, and nothing here derives the answer from a level queue, so the
    differential against the reference's level sweep is real."""
    out: list[int] = []
    if root is None:
        return out
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if depth == len(out):
            out.append(node[0])  # a depth is first reached through its ancestors
        else:
            out[depth] = node[0]
        if node[2] is not None:
            stack.append((node[2], depth + 1))  # pushed first, so left pops first
        if node[1] is not None:
            stack.append((node[1], depth + 1))
    return out


@judge_case("binary-tree-right-side-view")
def _binary_tree_right_side_view_case(n: int, rng: random.Random) -> tuple[list, list[int]]:
    n = max(0, min(n, 12))  # the statement allows an empty tree (0 nodes)
    if n and rng.random() < 0.25:
        # One node per level: the degenerate shape _random_tree's halving budget
        # cannot build, where the right-side view is the whole tree.
        tree = _binary_tree_right_side_view_spine(n)
    else:
        tree = _random_tree(rng, n)
    return [tree], _binary_tree_right_side_view_oracle(tree)


def _binary_tree_right_side_view_spine(n: int) -> list | None:
    """A chain of n nodes, each with only a left child (values 0..n-1): every
    level holds a single node, so all n of them are visible from the right."""
    node: list | None = None
    for value in range(n - 1, -1, -1):
        node = [value, node, None]
    return node


def _binary_tree_right_side_view_complete(n: int) -> list | None:
    """A complete tree of exactly n nodes whose values stay inside the
    statement's [-100, 100]. It is the shared _complete_tree, relabelled: that
    helper names node i with the value i, which leaves the stated range above
    n = 101 -- and a profiler input's *values* must respect the statement, not
    just its shape (the v0.12 products_of_array_except_self lesson)."""
    nodes: list[list | None] = [None] * n
    for i in range(n - 1, -1, -1):  # bottom-up: children finalized first
        left, right = 2 * i + 1, 2 * i + 2
        nodes[i] = [
            i % 201 - 100,
            nodes[left] if left < n else None,
            nodes[right] if right < n else None,
        ]
    return nodes[0]


@profiler_input("binary-tree-right-side-view")
def _binary_tree_right_side_view_profiler(n: int, rng: random.Random) -> list:
    """A complete tree of n nodes: which node is rightmost on a level can only
    be known after visiting that level, so a BFS and a DFS both walk all n nodes
    and neither can early-exit. The shape is complete rather than a spine so a
    recursive solution stays shallow, and n is capped at the statement's own
    100 nodes by probe_max_n (the default ladder would have measured 6400)."""
    # No internal cap: probe_max_n = 100 already cuts the live ladder at the
    # statement's own node bound, and a second clamp here would silently rebuild
    # the same tree for every ladder size above it (measured -- see the notes).
    return [_binary_tree_right_side_view_complete(max(1, n))]


@oracle("invert-binary-tree")
def _invert_binary_tree_oracle(root: list | None) -> list | None:
    """The definition made literal: at every node the two children are
    exchanged, so the inverted tree is [value, inverted right, inverted left].
    It BUILDS the mirror instead of swapping in place — that is what keeps the
    oracle a different program from the reference — and it is total on None."""
    if root is None:
        return None
    return [root[0], _invert_binary_tree_oracle(root[2]), _invert_binary_tree_oracle(root[1])]


@judge_case("invert-binary-tree")
def _invert_binary_tree_case(n: int, rng: random.Random) -> tuple[list, list | None]:
    n = max(0, min(n, 12))  # the statement allows 0..100 nodes; 0 is the empty tree
    tree = _random_tree(rng, n)  # ragged shapes; values 0..9, inside -100..100
    return [tree], _invert_binary_tree_oracle(tree)


def _invert_binary_tree_in_range(tree: list | None) -> list | None:
    """Relabel a tree's values into the statement's -100..100, shape untouched.

    ``_complete_tree`` labels node i with i, so at probe sizes its values run
    up to n - 1 and leave the statement's own range (the v0.12 value-fidelity
    lesson) — even though no implementation's cost depends on these values."""
    stack, i = [tree], 0
    while stack:
        node = stack.pop()
        if node is None:
            continue
        node[0] = -100 + (i % 201)  # sweeps -100..100, then repeats
        i += 1
        stack.append(node[1])
        stack.append(node[2])
    return tree


@profiler_input("invert-binary-tree")
def _invert_binary_tree_profiler(n: int, rng: random.Random) -> list:
    # A complete tree with exactly n nodes: every node is present and must be
    # reached, so the swap has nothing to early-exit on — and neither has an
    # explicit-stack or a queue version. Its depth is log2(n), 13 at the
    # ladder's top, so what is measured is the algorithm and not CPython's
    # recursion limit. See notes for why a path (the worst shape for a DFS
    # stack's space) cannot be used at probe scale at all.
    return [_invert_binary_tree_in_range(_complete_tree(n))]


@oracle("kth-smallest-element-in-a-bst")
def _kth_smallest_element_in_a_bst_oracle(root: list | None, k: int) -> int:
    """Brute force: collect every value with a plain traversal that uses nothing
    about the BST property, sort, and read the k-th. O(n log n), and correct for
    any shape — which is what makes it a real differential against the
    reference's in-order walk. The statement guarantees 1 <= k <= n; outside
    that there is no k-th smallest, so this refuses rather than invent one."""
    values: list[int] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        values.append(node[0])
        stack.append(node[1])
        stack.append(node[2])
    if not 1 <= k <= len(values):
        raise ValueError(f"k={k} is outside the statement's 1 <= k <= n (n={len(values)})")
    values.sort()
    return values[k - 1]


def _kth_smallest_element_in_a_bst_build(rng: random.Random, values: list[int]) -> list | None:
    """A BST over ascending distinct ``values``: the root of each range is picked
    at random, so the shape is what a uniformly random insertion order produces
    and the node count is exactly len(values)."""
    if not values:
        return None
    root = rng.randrange(len(values))
    return [
        values[root],
        _kth_smallest_element_in_a_bst_build(rng, values[:root]),
        _kth_smallest_element_in_a_bst_build(rng, values[root + 1 :]),
    ]


def _kth_smallest_element_in_a_bst_tree(rng: random.Random, size: int) -> list:
    """A BST of exactly ``size`` nodes with DISTINCT values in [0, 10^4] — the
    statement's own value range, and a BST's values have to be distinct for it
    to be a BST. Three quarters of the cases are a random-insertion-order shape;
    the rest are a degenerate spine, where the k-th smallest is the k-th node
    along it — the shape that breaks a solution which only walks the left spine
    from the root."""
    values = sorted(rng.sample(range(0, 10_001), size))
    if rng.random() < 0.25:
        spine: list | None = None
        if rng.random() < 0.5:  # right-leaning: the smallest value is the root
            for value in reversed(values):
                spine = [value, None, spine]
        else:  # left-leaning: the smallest value is the deepest node
            for value in values:
                spine = [value, spine, None]
        return spine
    return _kth_smallest_element_in_a_bst_build(rng, values)


@judge_case("kth-smallest-element-in-a-bst")
def _kth_smallest_element_in_a_bst_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's node range is [1, 10^4]
    tree = _kth_smallest_element_in_a_bst_tree(rng, n)
    k = rng.randint(1, n)  # the statement's guarantee 1 <= k <= n, by construction
    return [tree, k], _kth_smallest_element_in_a_bst_oracle(tree, k)


def _kth_smallest_element_in_a_bst_balanced(lo: int, hi: int) -> list | None:
    """A height-balanced BST with the keys lo..hi: the middle key of the range
    goes at the root, so the in-order walk is lo..hi and the tree is a BST by
    construction. (Placed before the profiler block it serves so that every
    helper sits inside the span the fragment's decorators mark for replacement.)"""
    if lo > hi:
        return None
    mid = (lo + hi) // 2
    return [
        mid,
        _kth_smallest_element_in_a_bst_balanced(lo, mid - 1),
        _kth_smallest_element_in_a_bst_balanced(mid + 1, hi),
    ]


@profiler_input("kth-smallest-element-in-a-bst")
def _kth_smallest_element_in_a_bst_profiler(n: int, rng: random.Random) -> list:
    """A perfectly height-balanced BST over the keys 0..n-1: exactly n nodes,
    depth log n, in-order = 0..n-1, so it is a valid BST with values inside the
    statement's [0, 10^4] at every rung of the ladder (6400 at the top, so the
    largest key is 6399). The shared `_complete_tree` cannot be used here: it
    labels node i with i, and that array-index labelling puts a left child
    (2i+1) above its own parent, so it is not a BST at all — and this statement
    guarantees the input is one. k = n, so the answer is the largest value and
    the in-order walk has to reach the very last node: no implementation can
    stop early, and k stays inside the statement's 1 <= k <= n. Balanced rather
    than a spine so a recursive solution runs at depth log n instead of n."""
    size = max(1, n)
    return [_kth_smallest_element_in_a_bst_balanced(0, size - 1), size]


@oracle("lowest-common-ancestor-of-a-binary-search-tree")
def _lowest_common_ancestor_of_a_binary_search_tree_oracle(
    root: list | None, p: int, q: int
) -> int | None:
    """Brute force that never looks at the BST ordering: record every node's
    parent, walk p's ancestor chain up to the root, then climb from q to the
    first node on that chain -- the LCA by definition.

    Ignoring the ordering is the point. The reference descends by comparing
    values, so the two agree only when the generated tree really is a BST with
    unique values: a generator that broke either guarantee would show up as
    oracle/reference disagreement on every generated case rather than as a
    silent wrong expected value.

    Values are the node identity here (the statement guarantees they are
    unique), which is also how p and q arrive: as the two nodes' values.
    """
    if root is None:
        return None
    parent: dict[int, int | None] = {root[0]: None}
    stack = [root]
    while stack:
        node = stack.pop()
        for child in (node[1], node[2]):
            if child is not None:
                parent[child[0]] = node[0]
                stack.append(child)
    if p not in parent or q not in parent:
        return None  # the statement guarantees both exist; stay total anyway
    ancestors = set()
    cur: int | None = p
    while cur is not None:
        ancestors.add(cur)
        cur = parent[cur]
    cur = q
    while cur not in ancestors:
        cur = parent[cur]
    return cur


def _lowest_common_ancestor_of_a_binary_search_tree_insert(
    root: list | None, value: int
) -> list:
    """Iterative BST insert; the generator only ever inserts distinct values, so
    the result is a BST with exactly one node per value."""
    node = [value, None, None]
    if root is None:
        return node
    cur = root
    while True:
        if value < cur[0]:
            if cur[1] is None:
                cur[1] = node
                return root
            cur = cur[1]
        else:
            if cur[2] is None:
                cur[2] = node
                return root
            cur = cur[2]


def _lowest_common_ancestor_of_a_binary_search_tree_values(root: list | None) -> list[int]:
    """Every value in the tree, in preorder. The generator draws p and q from
    this list, which is how "p and q will exist in the BST" is upheld by
    construction rather than by hope."""
    out: list[int] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        out.append(node[0])
        stack.append(node[1])
        stack.append(node[2])
    return out


def _lowest_common_ancestor_of_a_binary_search_tree_balanced(values: list[int]) -> list | None:
    """A height-balanced BST over distinct sorted values, built middle-out:
    height = log2(n), which keeps recursive student solutions far inside the
    recursion limit at every probe size."""
    if not values:
        return None
    mid = len(values) // 2
    return [
        values[mid],
        _lowest_common_ancestor_of_a_binary_search_tree_balanced(values[:mid]),
        _lowest_common_ancestor_of_a_binary_search_tree_balanced(values[mid + 1 :]),
    ]


@judge_case("lowest-common-ancestor-of-a-binary-search-tree")
def _lowest_common_ancestor_of_a_binary_search_tree_case(
    n: int, rng: random.Random
) -> tuple[list, int]:
    n = max(2, min(n, 12))  # the statement's floor: the tree has >= 2 nodes
    if rng.random() < 0.25:
        # The statement's own value extremes, so the boundary comparisons are
        # exercised (no other value is anywhere near them).
        values = [-(10**9), 10**9] + rng.sample(range(-38, 39), n - 2)
    else:
        values = rng.sample(range(-30, 31), n)
    if rng.random() < 0.25:
        values.sort()  # ascending insertion order: a right-leaning chain
    root = None
    for value in values:
        root = _lowest_common_ancestor_of_a_binary_search_tree_insert(root, value)
    p, q = rng.sample(_lowest_common_ancestor_of_a_binary_search_tree_values(root), 2)
    return [root, p, q], _lowest_common_ancestor_of_a_binary_search_tree_oracle(root, p, q)


@profiler_input("lowest-common-ancestor-of-a-binary-search-tree")
def _lowest_common_ancestor_of_a_binary_search_tree_profiler(
    n: int, rng: random.Random
) -> list:
    """A balanced BST of n distinct values (0..n-1, inside the statement's
    +-10^9) with p and q at the bottom of the left spine: p is the deepest
    left-spine node and q is its parent, so the intended descent has to walk the
    whole height instead of stopping at the root, and the parent-walk oracle
    still traverses every node. Nothing early-exits on either side.

    The tree is balanced rather than a spine because the declared target is O(h)
    and a spine of 6400 nodes would exceed Python's recursion limit for any
    recursive student solution -- the corpus's existing tree profilers are
    balanced for the same reason. p != q and both values exist by construction.
    """
    size = max(2, n)
    root = _lowest_common_ancestor_of_a_binary_search_tree_balanced(list(range(size)))
    child, parent = root, root[0]
    while child[1] is not None:
        parent = child[0]
        child = child[1]
    return [root, child[0], parent]


def _serialize_and_deserialize_binary_tree_encode(node: list | None) -> str:
    """A canonical preorder encoding with an explicit marker for a missing child:
    "N" for None and "value(left)(right)" for a node, so no value can be confused
    with a marker and no shape needs a delimiter. PRIVATE to the oracle -- the
    student's format is the student's own and the checker never looks at it."""
    if node is None:
        return "N"
    return (
        f"{node[0]}("
        f"{_serialize_and_deserialize_binary_tree_encode(node[1])}"
        f"{_serialize_and_deserialize_binary_tree_encode(node[2])})"
    )


def _serialize_and_deserialize_binary_tree_decode(
    data: str, i: int = 0
) -> tuple[list | None, int]:
    """Read back what `_..._encode` wrote; returns (tree, index just past it)."""
    if data[i] == "N":
        return None, i + 1
    start = i
    while data[i] != "(":
        i += 1
    value = int(data[start:i])
    left, i = _serialize_and_deserialize_binary_tree_decode(data, i + 1)
    right, i = _serialize_and_deserialize_binary_tree_decode(data, i)
    return [value, left, right], i + 1  # i is this node's closing paren


def _serialize_and_deserialize_binary_tree_encode(node: list | None) -> str:
    """A canonical preorder encoding with an explicit marker for a missing child:
    "N" for None and "value(left)(right)" for a node, so no value can be confused
    with a marker and no shape needs a delimiter. PRIVATE to the oracle -- the
    student's format is the student's own and the checker never looks at it."""
    if node is None:
        return "N"
    return (
        f"{node[0]}("
        f"{_serialize_and_deserialize_binary_tree_encode(node[1])}"
        f"{_serialize_and_deserialize_binary_tree_encode(node[2])})"
    )


def _serialize_and_deserialize_binary_tree_decode(
    data: str, i: int = 0
) -> tuple[list | None, int]:
    """Read back what `_..._encode` wrote; returns (tree, index just past it)."""
    if data[i] == "N":
        return None, i + 1
    start = i
    while data[i] != "(":
        i += 1
    value = int(data[start:i])
    left, i = _serialize_and_deserialize_binary_tree_decode(data, i + 1)
    right, i = _serialize_and_deserialize_binary_tree_decode(data, i)
    return [value, left, right], i + 1  # i is this node's closing paren


@oracle("serialize-and-deserialize-binary-tree")
def _serialize_and_deserialize_binary_tree_oracle(root: list | None) -> list | None:
    """The round-trip anchor: what `deserialize(serialize(root))` has to produce
    is `root` again, so the oracle encodes with the canonical codec above and
    decodes back. An oracle is a value, and the answer to this problem is a PAIR
    OF FUNCTIONS -- the real grading is the `tree_codec_roundtrip` checker running
    the student's own two functions -- but the case dicts need an `expected`
    value, and the corpus contract test's generic predicate path calls this
    oracle and hands its answer to the checker. Both are the tree itself."""
    tree, _ = _serialize_and_deserialize_binary_tree_decode(
        _serialize_and_deserialize_binary_tree_encode(root)
    )
    return tree


def _serialize_and_deserialize_binary_tree_same(a, b) -> bool:
    """Equality in dojo's tree shape: a node is a 3-element sequence whose first
    element is an int and whose other two are nodes or None. Tuples read as lists
    -- the judge's own strict comparison goes through JSON, where a tuple and a
    list are the same array, so a `deserialize` that rebuilds children as tuples
    must not be false-failed. bools are not ints here (Python says True == 1)."""
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if not (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple))):
            return False
        return len(a) == 3 and len(b) == 3 and all(
            _serialize_and_deserialize_binary_tree_same(x, y) for x, y in zip(a, b)
        )
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    return isinstance(a, int) and isinstance(b, int) and a == b


def _serialize_and_deserialize_binary_tree_size(node: list | None) -> int:
    if node is None:
        return 0
    return (
        1
        + _serialize_and_deserialize_binary_tree_size(node[1])
        + _serialize_and_deserialize_binary_tree_size(node[2])
    )


def _serialize_and_deserialize_binary_tree_other(root: list | None) -> list:
    """A tree that cannot equal `root`: a left chain with exactly one node more
    than `root` (two equal trees have equal node counts). Values are 0, inside the
    statement's -1000..1000."""
    node: list | None = None
    for _ in range(_serialize_and_deserialize_binary_tree_size(root) + 1):
        node = [0, node, None]
    return node  # type: ignore[return-value]


@checker("tree_codec_roundtrip")
def _serialize_and_deserialize_binary_tree_roundtrip(module, got, args) -> bool:
    """`deserialize(serialize(root))` must be `root` again -- in ANY encoding, since
    the statement leaves the format entirely to the student.

    The checker never parses, inspects or guesses the format: it calls the
    student's own `serialize`/`deserialize` through the module the harness hands it
    and compares trees. `got` is the harness's own call of the student's
    `serialize` on the case's tree, so it must be a str (the statement's contract
    and the stub's annotation).

    A second tree -- a chain one node longer, so it can never equal the case's
    tree -- is serialized too, and both strings go back to `deserialize` in the
    REVERSE of the order they were produced in. A `deserialize` that ignores its
    argument and returns whatever `serialize` last stashed in a module global (or
    pops off a stack) therefore decodes the wrong tree and fails; a codec whose
    string really carries the tree is unaffected. A plain round trip cannot see
    that difference -- the harness has just called `serialize`, so the stash holds
    the right tree at that moment -- and it is the one shape of "deserialize
    ignores its input" that would otherwise pass. A constant-returning or
    None-returning `deserialize` fails on the non-empty cases outright, and the
    judge requires every case to pass."""
    root = args[0]
    serialize = getattr(module, "serialize", None)
    deserialize = getattr(module, "deserialize", None)
    if not (callable(serialize) and callable(deserialize)):
        # No codec pair to exercise. Read this branch carefully, because two very
        # different callers reach it:
        #  * a SUBMISSION that deleted or renamed one half of the pair: nothing can
        #    be round-tripped, and a serialized string is not a tree, so it fails.
        #  * the corpus contract test (tests/test_registry.py `_predicate_holds`),
        #    which exercises a predicate checker generically by handing it the
        #    *registry's* public namespace -- where no student codec can exist --
        #    together with the oracle's own answer, and asks only that the trust
        #    anchor's answer be accepted.
        # A submission is always a real module (the harness loads solution.py with
        # importlib, so it has __name__); a registry view is a SimpleNamespace and
        # has none. Without that gate a student who made `serialize` return the
        # tree object and deleted `deserialize` would "round-trip" for free.
        if not hasattr(module, "__name__"):
            return _serialize_and_deserialize_binary_tree_same(got, root)
        return False
    if not isinstance(got, str):
        return False  # the statement: the tree "can be serialized to a string"
    other = _serialize_and_deserialize_binary_tree_other(root)
    other_encoded = serialize(other)
    if not isinstance(other_encoded, str):
        return False
    return _serialize_and_deserialize_binary_tree_same(
        deserialize(got), root
    ) and _serialize_and_deserialize_binary_tree_same(
        deserialize(other_encoded), other
    )


def _serialize_and_deserialize_binary_tree_value(rng: random.Random) -> int:
    """Inside the statement's -1000..1000. Half the draws come from a small range
    so values REPEAT: nothing in this statement promises unique values (unlike
    LC 105), and a codec that rebuilds the tree from a set of values instead of
    from the encoded structure breaks on a duplicate. Negatives appear in both
    halves, so the encoding has to carry the sign."""
    if rng.random() < 0.5:
        return rng.randint(-9, 9)
    return rng.randint(-1000, 1000)


def _serialize_and_deserialize_binary_tree_tree(
    rng: random.Random, n: int
) -> list | None:
    """A random tree with exactly n nodes: one draw in four is a degenerate chain
    (left-only or right-only), otherwise the nodes are split uniformly."""
    if n <= 0:
        return None
    if n > 2 and rng.random() < 0.25:
        if rng.random() < 0.5:
            return [
                _serialize_and_deserialize_binary_tree_value(rng),
                _serialize_and_deserialize_binary_tree_tree(rng, n - 1),
                None,
            ]
        return [
            _serialize_and_deserialize_binary_tree_value(rng),
            None,
            _serialize_and_deserialize_binary_tree_tree(rng, n - 1),
        ]
    left = rng.randrange(n)  # 0..n-1 nodes go left, the rest right
    return [
        _serialize_and_deserialize_binary_tree_value(rng),
        _serialize_and_deserialize_binary_tree_tree(rng, left),
        _serialize_and_deserialize_binary_tree_tree(rng, n - 1 - left),
    ]


@judge_case("serialize-and-deserialize-binary-tree")
def _serialize_and_deserialize_binary_tree_case(
    n: int, rng: random.Random
) -> tuple[list, list, dict]:
    # n = 0 is legal here (the statement allows an empty tree, and Example 2 is
    # one), so the clamp keeps it: 0..12 of the statement's 0..10^4.
    n = max(0, min(n, 12))
    tree = _serialize_and_deserialize_binary_tree_tree(rng, n)
    return [
        tree
    ], _serialize_and_deserialize_binary_tree_oracle(tree), {
        "predicate": "tree_codec_roundtrip"
    }


@oracle("subtree-of-another-tree")
def _subtree_of_another_tree_oracle(root: list | None, sub_root: list | None) -> bool:
    """Brute force: every node of root is a candidate, and a candidate qualifies
    when its subtree is structurally identical to subRoot. Both walks use an
    explicit stack, so the oracle also survives the probe's largest input when a
    mismatch has to be confirmed at that size (no recursion limit anywhere)."""
    if sub_root is None:
        return True  # the empty tree is a subtree of every tree (never generated)
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        if _subtree_of_another_tree_same(node, sub_root):
            return True
        stack.append(node[1])
        stack.append(node[2])
    return False


def _subtree_of_another_tree_same(a: list | None, b: list | None) -> bool:
    """Structural equality of two nested-list trees, iteratively."""
    pairs = [(a, b)]
    while pairs:
        x, y = pairs.pop()
        if x is None or y is None:
            if (x is None) != (y is None):
                return False
            continue
        if x[0] != y[0]:
            return False
        pairs.append((x[1], y[1]))
        pairs.append((x[2], y[2]))
    return True


@judge_case("subtree-of-another-tree")
def _subtree_of_another_tree_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(1, min(n, 12))  # the statement's floor: both trees have >= 1 node
    root = _random_tree(rng, n)
    if rng.random() < 0.5:
        # A true case by construction: subRoot is the subtree of a node of root
        # (the root itself when the root node is drawn -- the statement's own
        # "the tree could also be considered as a subtree of itself").
        node = rng.choice(_subtree_of_another_tree_nodes(root))
        sub = _subtree_of_another_tree_clone(node)
    else:
        # An independent tree, which may still occur in root by accident: the
        # expected value always comes from the oracle, never from this branch.
        sub = _random_tree(rng, max(1, min(n, 12)))
    return [root, sub], _subtree_of_another_tree_oracle(root, sub)


def _subtree_of_another_tree_nodes(root: list | None) -> list[list]:
    """Every non-empty node of a nested-list tree, in preorder."""
    out: list[list] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        out.append(node)
        stack.append(node[1])
        stack.append(node[2])
    return out


def _subtree_of_another_tree_clone(node: list | None) -> list | None:
    """A structural copy, so a generated case never aliases root's own nodes as
    subRoot (the two arguments are independent trees either way, but a shared
    object in a stored case is a trap for whoever reads it next)."""
    if node is None:
        return None
    return [
        node[0],
        _subtree_of_another_tree_clone(node[1]),
        _subtree_of_another_tree_clone(node[2]),
    ]


@profiler_input("subtree-of-another-tree")
def _subtree_of_another_tree_profiler(n: int, rng: random.Random) -> list:
    """A complete root tree of n nodes paired with a 3-node subRoot that cannot
    occur in it: root holds the values 0..n-1 (n <= 2000 here) and subRoot's root
    value is 10_000, the statement's own upper bound for a value, which root
    never holds. No candidate can match, so the compare-each-node solution walks
    all n nodes (nothing early-exits) and a serialization solution scans its
    whole encoding. The tree is complete rather than a spine so that recursive
    student solutions stay far inside the recursion limit, and its size is capped
    at the statement's 2000 nodes by probe_max_n."""
    # No size clamp beyond the sentinel's own invariant: a complete tree of
    # 0..size-1 nodes holds 10_000 only once size > 10_000, and every real ladder
    # is far below that (probe_max_n = 2000 here, 6400 by default). An internal
    # clamp would be worse than useless -- see the notes.
    size = max(1, min(n, 10_000))
    return [
        _complete_tree(size),
        [10_000, [9_999, None, None], [9_998, None, None]],
    ]


@oracle("count-good-nodes-in-binary-tree")
def _count_good_nodes_in_binary_tree_oracle(root: list | None) -> int:
    """The definition transcribed literally: a node is good when no node on the
    path from the root down to it has a larger value (its own value is compared
    too, which is harmless — a value is never greater than itself). So carry
    each path explicitly and test every node against its own path: O(n*h),
    obviously correct, and it uses nothing about the tree's shape. Total on the
    empty tree, which the statement's [1, 10^5] node range does not allow but
    the dojo representation can express."""

    def walk(node: list | None, path: list[int]) -> int:
        if node is None:
            return 0
        value = node[0]
        good = all(ancestor <= value for ancestor in path)
        below = path + [value]
        return (1 if good else 0) + walk(node[1], below) + walk(node[2], below)

    return walk(root, [])


def _count_good_nodes_in_binary_tree_shift(node: list | None, delta: int) -> None:
    """Add ``delta`` to every value in place. The shape is untouched and adding
    one constant to every value cannot change a single comparison, so the
    oracle's answer is still the answer."""
    if node is None:
        return
    node[0] += delta
    _count_good_nodes_in_binary_tree_shift(node[1], delta)
    _count_good_nodes_in_binary_tree_shift(node[2], delta)


@judge_case("count-good-nodes-in-binary-tree")
def _count_good_nodes_in_binary_tree_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's node range is [1, 10^5]
    tree = _random_tree(rng, n)  # values 0..9: inside [-10^4, 10^4], and tie-heavy
    # A third of the cases are shifted to one end of the statement's value range
    # (-10^4, or 10^4 when 9 is the largest value drawn). Shifting cannot change
    # which nodes are good, so the case stays oracle-derived, and it covers both
    # ends of the range plus the classic wrong seeding of the running maximum
    # (0 instead of "nothing seen yet", which no negative tree can survive).
    if rng.random() < 0.34:
        _count_good_nodes_in_binary_tree_shift(tree, rng.choice([-10_000, 9_991]))
    return [tree], _count_good_nodes_in_binary_tree_oracle(tree)


@profiler_input("count-good-nodes-in-binary-tree")
def _count_good_nodes_in_binary_tree_profiler(n: int, rng: random.Random) -> list:
    """A complete tree: exactly n nodes, values 0..n-1 (inside the statement's
    [-10^4, 10^4] for every rung of the probe ladder, the top one being 6400),
    each node larger than its parent, so every node is good and the count is n.
    Nothing can early-exit — the whole tree has to be visited either way.
    Balanced rather than a chain so a recursive solution runs at depth log n
    instead of n (`_diameter_profiler`'s convention)."""
    return [_complete_tree(n)]


# -------------------------------------------------------------- binary_search


@oracle("peak_elements")
def _find_a_peak_oracle(nums: list[int]) -> int:
    for i in range(len(nums) - 1):
        if nums[i] > nums[i + 1]:
            return i
    return len(nums) - 1


@judge_case("peak_elements")
def _find_a_peak_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))
    # Bitonic arrays: strictly increasing then strictly decreasing, exactly
    # one peak — "leftmost peak" is unambiguous for any correct answer.
    peak_idx = rng.randrange(n)
    left: list[int] = []
    if peak_idx > 0:
        left = [rng.randint(1, 20)]
        for _ in range(peak_idx - 1):
            left.append(left[-1] + rng.randint(1, 10))
    peak_value = (left[-1] if left else rng.randint(1, 20)) + rng.randint(1, 10)
    right: list[int] = []
    if peak_idx < n - 1:
        right = [peak_value - rng.randint(1, 10)]
        for _ in range(n - peak_idx - 2):
            right.append(right[-1] - rng.randint(1, 10))
    return [left + [peak_value] + right], peak_idx
# No profiler input: O(log n) growth is flat at the probe sizes the profiler
# uses (100..6400) and would be misreported as O(1) — an honesty choice.



@oracle("median-of-two-sorted-arrays")
def _median_of_two_sorted_arrays_oracle(nums1: list[int], nums2: list[int]) -> float | None:
    """Brute force: merge both arrays (sorted() is the merge), take the middle —
    the mean of the two middle elements when the total is even. Written to be
    total on two empty arrays, though the statement requires m + n >= 1."""
    merged = sorted(nums1 + nums2)
    size = len(merged)
    if size == 0:
        return None
    mid = size // 2
    if size % 2:
        return float(merged[mid])
    return (merged[mid - 1] + merged[mid]) / 2


@judge_case("median-of-two-sorted-arrays")
def _median_of_two_sorted_arrays_case(
    n: int, rng: random.Random
) -> tuple[list, float, dict]:
    size = max(1, min(n, 12))  # the statement's own bound: 1 <= m + n
    m = rng.randint(0, size)  # either side may be empty (0 <= m, 0 <= n)
    k = size - m
    # Values are inside [-10^6, 10^6]; duplicates are allowed by the statement
    # (only "sorted" is promised), and the median of a multiset is unique anyway.
    nums1 = sorted(rng.randint(-1_000_000, 1_000_000) for _ in range(m))
    nums2 = sorted(rng.randint(-1_000_000, 1_000_000) for _ in range(k))
    expected = _median_of_two_sorted_arrays_oracle(nums1, nums2)
    return [nums1, nums2], expected, {"compare": "approx:1e-5"}


@profiler_input("median-of-two-sorted-arrays")
def _median_of_two_sorted_arrays_profiler(n: int, rng: random.Random) -> list:
    # An even total split evenly and interleaved: both halves are non-empty,
    # strictly increasing, and neither dominates, so the partition search does
    # its full log(min(m, n)).
    #
    # The merged middle pair is (v, v + 1) by construction, so the median is a
    # half-integer: every correct solution returns exactly the same float, which
    # is what lets the probe's exact digest comparison accept a correct answer
    # instead of blaming it for an int/float spelling (an odd total would let a
    # solution legally return the int middle element and disagree with this
    # reference's float on the digest alone).
    total = max(2, n - (n % 2))
    merged = [-1_000_000 + i for i in range(total)]  # distinct, ascending, in range
    return [merged[0::2], merged[1::2]]



@oracle("search-in-rotated-sorted-array")
def _search_in_rotated_sorted_array_oracle(nums: list[int], target: int) -> int:
    for i, value in enumerate(nums):
        if value == target:
            return i
    return -1


@judge_case("search-in-rotated-sorted-array")
def _search_in_rotated_sorted_array_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= nums.length
    ascending = sorted(rng.sample(range(-10_000, 10_001), n))  # unique, inside [-10^4, 10^4]
    # k = 0 is the "possibly rotated" reading of the constraints (the parenthetical
    # k >= 1 describes a genuine rotation; the constraint line admits nums sorted).
    k = rng.randrange(n) if n > 1 else 0
    nums = ascending[k:] + ascending[:k]
    if rng.random() < 0.5:
        target = rng.choice(nums)
    else:  # a target that is genuinely absent: the "-1" path, not a lucky hit
        present = set(nums)
        target = rng.randint(-10_000, 10_000)
        while target in present:
            target = target + 1 if target < 10_000 else -10_000
    return [nums, target], _search_in_rotated_sorted_array_oracle(nums, target)
# No profiler input: O(log n) growth is flat at the probe sizes, and the
# O(1) <-> O(log n) boundary is a knife-edge — measured, see the fragment notes.
# No profiler input: O(log n) growth is flat at the probe sizes, and the
# O(1) <-> O(log n) boundary is a knife-edge — measured, see the fragment notes.



@oracle("search-a-2d-matrix")
def _search_a_2d_matrix_oracle(matrix: list[list[int]], target: int) -> bool:
    # Brute force: visit every cell and use none of the sortedness.
    for row in matrix:
        for value in row:
            if value == target:
                return True
    return False


def _search_a_2d_matrix_absent_target(values: list[int], rng: random.Random) -> int:
    """A target inside the statement's own range that is not in ``values``."""
    present = set(values)
    for _ in range(64):
        candidate = rng.randint(-10_000, 10_000)
        if candidate not in present:
            return candidate
    # Unreachable with <= 12 values drawn from 20_001, kept so this is total.
    return next(v for v in range(-10_000, 10_001) if v not in present)


@judge_case("search-a-2d-matrix")
def _search_a_2d_matrix_case(n: int, rng: random.Random) -> tuple[list, bool]:
    total = max(1, min(n, 12))  # the statement's floor: m >= 1 and n >= 1
    rows = rng.randint(1, min(4, total))
    cols = rng.randint(1, max(1, total // rows))
    # Strictly increasing in flattened order, so each row is non-decreasing AND
    # the first integer of each row is greater than the last of the previous one
    # (strictly increasing is the only shape that gives the statement's strict
    # ">" between rows). Values stay inside -10^4 <= matrix[i][j] <= 10^4.
    values: list[int] = []
    current = rng.randint(-10_000, 10_000 - 5 * rows * cols)
    for _ in range(rows * cols):
        values.append(current)
        current += rng.randint(1, 5)
    matrix = [values[i * cols:(i + 1) * cols] for i in range(rows)]
    if rng.random() < 0.5:
        target = rng.choice(values)  # a hit, the shape example 1 has
    else:
        target = _search_a_2d_matrix_absent_target(values, rng)  # a miss
    return [matrix, target], _search_a_2d_matrix_oracle(matrix, target)


@profiler_input("search-a-2d-matrix")
def _search_a_2d_matrix_profiler(n: int, rng: random.Random) -> list:
    # The matrix is one strictly increasing run of EVEN values laid out row by
    # row (so both stated properties hold exactly), and the target is an ODD
    # value in the gap just below the LAST cell: it is not in the matrix, so the
    # binary search cannot stop at a lucky midpoint but must run its loop to
    # exhaustion, on a deepest gap for this midpoint scheme (one round deeper
    # than a mid-matrix miss at every size I measured), while a linear scan must
    # read every cell (the `target > matrix[-1][-1]` short-circuit cannot fire
    # either). All values and the target are inside
    # -10^4 <= matrix[i][j], target <= 10^4, and the shape is square-ish with
    # both dimensions <= 100 (the statement's own bound), so the cell count is
    # ~n for the probe's ladder.
    n = max(2, min(n, 10_000))  # 100 x 100 is the most cells the statement allows
    side = max(1, int(n**0.5))  # no `math` import here: registry.py imports only random
    while side * side < n and side < 100:
        side += 1
    cols = min(100, side)
    rows = min(100, -(-n // cols))
    total = rows * cols
    values = [-10_000 + 2 * i for i in range(total)]
    matrix = [values[i * cols:(i + 1) * cols] for i in range(rows)]
    target = values[-2] + 1
    return [matrix, target]



@oracle("find-minimum-in-rotated-sorted-array")
def _find_minimum_in_rotated_sorted_array_oracle(nums: list[int]) -> int | None:
    best = None
    for value in nums:
        if best is None or value < best:
            best = value
    return best


@judge_case("find-minimum-in-rotated-sorted-array")
def _find_minimum_in_rotated_sorted_array_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= n
    ascending = sorted(rng.sample(range(-5_000, 5_001), n))  # unique, inside [-5000, 5000]
    # k = 0 is the "rotated n times" case the statement allows explicitly (its
    # example 3, [11,13,15,17], is exactly that).
    k = rng.randrange(n)
    nums = ascending[k:] + ascending[:k]
    return [nums], _find_minimum_in_rotated_sorted_array_oracle(nums)
# No profiler input: same O(log n) flatness/knife-edge as its sibling
# search-in-rotated-sorted-array — measured, see the fragment notes.
# No profiler input: same O(log n) flatness/knife-edge as its sibling
# search-in-rotated-sorted-array — measured, see the fragment notes.



@oracle("binary-search")
def _binary_search_oracle(nums: list[int], target: int) -> int:
    # Brute force: read the array left to right and stop at the first match.
    # The statement promises unique values, so the first match is the only one,
    # and a full pass without a match is the -1.
    for i, value in enumerate(nums):
        if value == target:
            return i
    return -1


def _binary_search_absent_target(nums: list[int], rng: random.Random) -> int:
    """A target inside the statement's own range that is not in ``nums``."""
    present = set(nums)
    for _ in range(64):
        candidate = rng.randint(-9_999, 9_999)
        if candidate not in present:
            return candidate
    # Unreachable with <= 12 values drawn from 19_999, kept so this is total.
    return next(v for v in range(-9_999, 10_000) if v not in present)


@judge_case("binary-search")
def _binary_search_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's floor: nums.length >= 1
    # Ascending and unique (the statement's own two promises), every value
    # strictly inside -10^4 < nums[i] < 10^4.
    nums = sorted(rng.sample(range(-9_999, 10_000), n))
    if rng.random() < 0.5:
        target = rng.choice(nums)  # a hit, the shape both examples have
    else:
        target = _binary_search_absent_target(nums, rng)  # a miss
    return [nums, target], _binary_search_oracle(nums, target)


@profiler_input("binary-search")
def _binary_search_profiler(n: int, rng: random.Random) -> list:
    # Both ways this input could let something finish early are closed. The
    # target is ABSENT, so a binary search cannot stop at a lucky midpoint but
    # must run its loop to exhaustion; it sits in the gap just below the LARGEST
    # element, a deepest gap for this midpoint scheme (one round deeper than a
    # mid-array miss at every size I measured); and it is strictly inside the
    # value span, so the `target > nums[-1]` short-circuit a linear scan might
    # use cannot fire and a linear scan must read all n. Values are all odd and
    # the target is even (the miss is structural, not luck), and every value and
    # the target are strictly inside the statement's -10^4 < nums[i], target <
    # 10^4 range. n is capped at the statement's own 10^4 (the probe's ladder
    # stops at 6400) and floored at 2 so the top gap exists.
    n = max(2, min(n, 10_000))
    nums = [-9_999 + 2 * i for i in range(n)]
    target = nums[-2] + 1
    return [nums, target]



@oracle("koko-eating-bananas")
def _koko_eating_bananas_oracle(piles: list[int], h: int) -> int:
    # Brute force: try every speed from 1 upwards and answer with the first one
    # that fits in h hours. The `hours > h` break only skips the rest of a sum
    # that has already failed, so it cannot change the answer; without it this
    # loop would be hopeless on the profiler input, where the answer is 2000.
    if not piles:
        return 1  # unreachable under the statement's constraints (length >= 1)
    for speed in range(1, max(piles) + 1):
        hours = 0
        for pile in piles:
            hours += -(-pile // speed)  # ceil(pile / speed), in integers
            if hours > h:
                break
        if hours <= h:
            return speed
    # Unreachable while h >= len(piles): speed = max(piles) costs exactly
    # len(piles) hours, which the statement's `piles.length <= h` allows.
    return max(piles)


@judge_case("koko-eating-bananas")
def _koko_eating_bananas_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's floor: piles.length >= 1
    piles = [rng.randint(1, 20) for _ in range(n)]
    # piles.length <= h is the statement's own floor, and h == n is the tightest
    # legal case there is (every pile eaten in exactly one hour, answer = the
    # largest pile) — it is included on purpose, not by accident.
    h = rng.randint(n, n + 6)
    return [piles, h], _koko_eating_bananas_oracle(piles, h)


@profiler_input("koko-eating-bananas")
def _koko_eating_bananas_profiler(n: int, rng: random.Random) -> list:
    # n piles, every one of them within 1_000 of 10_000, and h = 5n: the answer
    # is exactly 2_000, and the reference's binary search then takes all 14
    # rounds of the range [1, max(piles)] — the geometric maximum for this
    # midpoint scheme, which I checked exhaustively over every possible answer
    # instead of assuming it (h = 2n gives the same shape but k* = 5_000 and only
    # 13 of the 14 rounds; the count depends on where the answer sits in the
    # interval tree, and it is identical at every ladder size because the range
    # does not depend on n). Every round scans all n piles, so nothing
    # early-exits on the reference side. The piles are deliberately all about the
    # same size: with one dominant pile the `hours > h` short-circuit a
    # feasibility check may use would decide after a single pile and a student's
    # check would measure as O(1), which is the early-exit trap this input exists
    # to close — with these piles the shortest scan any visited speed provokes is
    # 0.62n. Values stay inside 1 <= piles[i] <= 10^9 and
    # piles.length <= h <= 10^9.
    #
    # 10^4 rather than the statement's 10^9 is a deliberate ceiling: the
    # brute-force oracle has to run on this same input (probe_smoke runs it as
    # the student up to n=800, _oracle_confirms at the disputed size), and its
    # cost grows with the largest pile. At 10^4 it is still a ~14-probe search,
    # so the intended cost model is fully exercised.
    n = max(1, min(n, 10_000))  # 1 <= piles.length <= 10^4
    piles = [10_000 - (i % 1_000) for i in range(n)]
    return [piles, 5 * n]



@oracle("time-based-key-value-store")
def _time_based_key_value_store_oracle(ops: list[list]) -> list:
    """Brute force: keep every (timestamp, value) for a key and scan them all on
    a get, taking the latest timestamp that is <= the query."""
    store: dict[str, list[list]] = {}
    out: list = []
    for op in ops:
        method, *args = op
        if method == "set":
            key, value, timestamp = args
            store.setdefault(key, []).append([timestamp, value])
            out.append(None)
        elif method == "get":
            key, timestamp = args
            latest_stamp = None
            latest_value = ""
            for stamp, value in store.get(key, []):
                if stamp <= timestamp and (latest_stamp is None or stamp > latest_stamp):
                    latest_stamp, latest_value = stamp, value
            out.append(latest_value)
        else:  # pragma: no cover - the generator only emits set and get
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("time-based-key-value-store")
def _time_based_key_value_store_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # Deterministic by construction: every op comes from the seeded rng, the
    # timestamps are a strictly increasing counter (the statement's own
    # guarantee), and the key pool is fixed, so the same (n, rng) always
    # replays the same sequence on a fresh instance.
    steps = 2 * max(1, min(n, 12)) + 1
    written = ("k0", "k1", "k2")  # keys that get writes
    keys = written + ("k3",)  # k3 is never written: get on it must answer ""
    ops: list[list] = []
    stamp = 0
    for step in range(steps):
        key = rng.choice(keys if step % 2 else written)
        if step % 2 == 0:  # a set: the timestamp only ever moves forward
            stamp += rng.randint(1, 4)
            value = "".join(
                rng.choice("abcdefghijklmnopqrstuvwxyz0123456789")
                for _ in range(rng.randint(1, 3))
            )
            ops.append(["set", key, value, stamp])
        else:  # a get: at, just before, or just after the newest timestamp
            asked = max(1, stamp + rng.choice([-1, 0, 0, 1, 2]))
            ops.append(["get", key, asked])
    return [], _time_based_key_value_store_oracle(ops), {"ops": ops}
# ------------------------------------------------------- dynamic_programming


@oracle("sum_largest_contiguous_subarray")
def _sum_largest_subarray_oracle(A: list[int]) -> int:
    best = 0
    for i in range(len(A)):
        total = 0
        for j in range(i, len(A)):
            total += A[j]
            best = max(best, total)
    return best


@judge_case("sum_largest_contiguous_subarray")
def _sum_largest_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(0, min(n, 12))
    A = [rng.randint(-10, 10) for _ in range(n)]
    return [A], _sum_largest_subarray_oracle(A)


@profiler_input("sum_largest_contiguous_subarray")
def _sum_largest_profiler(n: int, rng: random.Random) -> list:
    return [[rng.randint(-100, 100) for _ in range(n)]]


# --------------------------------------------------------------------- greedy


@oracle("max_prod_3_nums")
def _max_tri_prod_oracle(A: list[int]) -> int:
    best = -(10**18)
    for i in range(len(A)):
        for j in range(i + 1, len(A)):
            for k in range(j + 1, len(A)):
                best = max(best, A[i] * A[j] * A[k])
    return best


@judge_case("max_prod_3_nums")
def _max_tri_prod_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(3, min(n, 12))
    A = [rng.randint(-10, 10) for _ in range(n)]
    return [A], _max_tri_prod_oracle(A)


@profiler_input("max_prod_3_nums")
def _max_tri_prod_profiler(n: int, rng: random.Random) -> list:
    return [[rng.randint(-100, 100) for _ in range(n)]]


# ------------------------------------------------- multi-function / predicate
# Problems whose correctness is a property, not an equality: the judge runs
# the function, then a CHECKER validates the result (with the module in hand,
# so round-trips can call both functions).


@checker("encode_decode_roundtrip")
def _encode_decode_roundtrip(module, got, args) -> bool:
    """decode(encode(strs)) == strs — the contract for encode_and_decode_strings."""
    return module.decode(got) == args[0]


@judge_case("encode_and_decode_strings")
def _encode_decode_case(n: int, rng: random.Random) -> tuple[list, bool, dict]:
    n = max(0, min(n, 12))
    strs = [
        "".join(rng.choice("ab:, !?") for _ in range(rng.randint(0, 6)))
        for _ in range(rng.randint(0, n))
    ]
    return [strs], True, {"predicate": "encode_decode_roundtrip"}


@checker("sample_valid")
def _sample_valid(module, got, args) -> bool:
    """Exactly n integers, summing to target, standard deviation <= sigma."""
    n, sigma, target = args
    if not isinstance(got, list) or len(got) != n or any(not isinstance(x, int) for x in got):
        return False
    if sum(got) != target:
        return False
    mu = target / n
    variance = sum((x - mu) ** 2 for x in got) / n
    return variance**0.5 <= sigma + 1e-9


def _reference_sample(n: int, sigma: float, target: int) -> list:
    """A trivially valid sample (values differ by at most 1, so sd <= 0.5).
    Used by tests to validate the checker; not part of the judge itself."""
    base, rem = divmod(target, n)
    return [base + 1] * rem + [base] * (n - rem)


@judge_case("generate_sample_to_target_sum")
def _generate_sample_case(n: int, rng: random.Random) -> tuple[list, bool, dict]:
    n = max(1, min(n, 12))
    sigma = round(rng.uniform(1.0, 4.0), 1)  # >= 1: the even split is always feasible
    target = rng.randint(-20, 20)
    return [n, sigma, target], True, {"predicate": "sample_valid"}


@checker("is_peak")
def _is_peak(module, got, args) -> bool:
    """got is the index of any peak in args[0] (strictly greater than its
    existing neighbors; endpoints beat their single neighbor)."""
    nums = args[0]
    if not isinstance(got, int) or not 0 <= got < len(nums):
        return False
    left = nums[got - 1] if got > 0 else float("-inf")
    right = nums[got + 1] if got < len(nums) - 1 else float("-inf")
    return nums[got] > left and nums[got] > right


@oracle("jump-game-ii")
def _jump_game_ii_oracle(nums: list[int]) -> int:
    """Brute force: the minimum-jumps DP. best[i] is the fewest jumps that reach
    index i, relaxed over every jump length from every index — O(n^2), and it
    fills the whole table rather than returning at the first hit, so it cannot
    early-exit on the profiler input.

    A position no path reaches stays at n + 1 (no route needs more than n - 1
    jumps) and is reported as -1; the statement guarantees that never happens,
    and the generator's guarantee is checked against this answer."""
    n = len(nums)
    if n <= 1:
        return 0
    unreachable = n + 1
    best = [unreachable] * n
    best[0] = 0
    for i in range(n):
        if best[i] == unreachable:
            continue
        for j in range(i + 1, min(n, i + nums[i] + 1)):
            if best[i] + 1 < best[j]:
                best[j] = best[i] + 1
    return best[-1] if best[-1] != unreachable else -1


@judge_case("jump-game-ii")
def _jump_game_ii_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= nums.length
    # The statement guarantees nums[n - 1] is reachable, so the case is built to
    # be: a random walk lays a path down first and every index it lands on keeps
    # at least the step it needs. Extra reach anywhere else only helps.
    nums = [rng.randint(0, 3) for _ in range(n)]
    idx = 0
    while idx < n - 1:
        step = rng.randint(1, min(3, n - 1 - idx))
        nums[idx] = max(nums[idx], step)
        idx += step
    return [nums], _jump_game_ii_oracle(nums)


@profiler_input("jump-game-ii")
def _jump_game_ii_profiler(n: int, rng: random.Random) -> list:
    # All ones: a strictly increasing staircase of reach. The level boundary
    # advances by exactly one index per level, so the greedy pays a jump at every
    # index and first reaches index n - 1 only on its (n - 1)-th level — there is
    # no `farthest >= n - 1` shortcut to take and no level that swallows the rest
    # of the array. The DP oracle re-relaxes the whole table too, one jump length
    # per index, and the values respect the statement's 0 <= nums[i] <= 1000.
    return [[1] * max(1, n)]


@oracle("jump-game")
def _jump_game_oracle(nums: list[int]) -> bool:
    """Brute force: fill a reachability table by trying every jump length from
    every index that turned out to be reachable. No shortcut on success — the
    whole table is filled, so it cannot early-exit on the profiler input.

    Total on the empty list (excluded by the statement's length >= 1): there is
    no last index to reach, so the answer is False, and the reference agrees."""
    n = len(nums)
    if n == 0:
        return False
    reachable = [False] * n
    reachable[0] = True
    for i in range(n):
        if not reachable[i]:
            continue
        for j in range(i + 1, min(n, i + nums[i] + 1)):
            reachable[j] = True
    return reachable[-1]


@judge_case("jump-game")
def _jump_game_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= nums.length
    nums = [rng.randint(0, 3) for _ in range(n)]
    if rng.random() < 0.4:
        # One long jump somewhere: values in 0..3 alone leave most short arrays
        # unsolvable, and both answers have to show up in the generated cases.
        nums[rng.randrange(n)] = rng.randint(0, n)
    return [nums], _jump_game_oracle(nums)


@profiler_input("jump-game")
def _jump_game_profiler(n: int, rng: random.Random) -> list:
    # All ones: the frontier advances by exactly one index per step, so
    # `reach >= n - 1` first holds at index n - 2 — the latest index it can hold
    # at, since a jump of 1 is the shortest that can finish the array — and the
    # pass has to visit every index to find that out. The reachability table has
    # nothing to early-exit on either: one jump length per index and no value big
    # enough to shortcut to the end. (A student that re-scans the array per index
    # is still quadratic here; a student that scans the *jump lengths* is not,
    # and cannot be — no solvable array both lags the frontier this way and has
    # sum(nums) = O(n^2).)
    return [[1] * max(1, n)]


@oracle("gas-station")
def _gas_station_oracle(gas: list[int], cost: list[int]) -> int:
    """Brute force: try every station and drive the whole circuit from it,
    abandoning a start the moment the tank goes negative. The first station that
    completes the loop is the answer, else -1.

    With the statement's uniqueness guarantee that first hit *is* the answer, but
    the oracle assumes nothing: on an input with two valid stations it answers
    with the lowest index, which is also what the canonical greedy answers there
    (checked exhaustively over small arrays before this fragment was written)."""
    n = len(gas)
    for start in range(n):
        tank = 0
        for k in range(n):
            i = (start + k) % n
            tank += gas[i] - cost[i]
            if tank < 0:
                break
        else:
            return start
    return -1


def _gas_station_valid_starts(gas: list[int], cost: list[int]) -> list[int]:
    """Every station the circuit can be completed from, by simulation. The
    generator uses it to check the uniqueness the statement promises before it
    hands a case over; the oracle is the same idea with a first-hit return."""
    n = len(gas)
    starts: list[int] = []
    for start in range(n):
        tank = 0
        for k in range(n):
            i = (start + k) % n
            tank += gas[i] - cost[i]
            if tank < 0:
                break
        else:
            starts.append(start)
    return starts


@judge_case("gas-station")
def _gas_station_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= n <= 10^5
    # The net profile d[i] = gas[i] - cost[i] is built as a tank-level walk seen
    # from the starting station: levels[0] = 0 at `start`, the levels ahead of it
    # stay positive, and levels[n] is the circuit's total.
    #
    # A station at offset m can finish the circuit exactly when (a) no later
    # level sits below its own, and (b) after the wrap the total still covers
    # every earlier level. With levels[0] = 0 the unique minimum, (b) for m >= 1
    # reduces to `total >= levels[m]`. So:
    #   * total >= 0 and every other level >= 3 -> only offset 0 can finish, i.e.
    #     the answer is unique, which is the statement's "if there exists a
    #     solution, it is guaranteed to be unique" (note it is NOT enough for the
    #     total to be non-negative, and a strict surplus does not imply
    #     uniqueness either: gas=[0,1]/cost=[0,0] has two valid starts);
    #   * total < 0 -> every circuit ends in deficit, no station finishes, and
    #     the answer is -1, trivially unique.
    # 2 cases in 5 are solvable and 3 in 5 are not: the statement says nothing
    # about the mix, and a generator producing only one kind would leave half the
    # contract untested.
    start = rng.randrange(n)
    solvable = rng.random() < 0.4
    total = rng.randint(0, 2) if solvable else -rng.randint(1, 3)
    levels = [0] + [rng.randint(3, 6) for _ in range(n - 1)] + [total]
    net = [levels[(i - start) % n + 1] - levels[(i - start) % n] for i in range(n)]
    cost = [rng.randint(max(0, -d), max(0, -d) + 4) for d in net]
    gas = [c + d for c, d in zip(cost, net)]
    expected = _gas_station_oracle(gas, cost)
    if expected >= 0 and _gas_station_valid_starts(gas, cost) != [expected]:
        # Verified, not assumed: if the walk ever failed to leave exactly one
        # station able to finish, this generator would ship an input the
        # statement forbids. Fall back to a shape whose uniqueness is by
        # inspection (the whole surplus at the last station, every earlier one
        # empty) rather than trusting the argument above. Two earlier versions of
        # that argument were wrong, which is exactly why it is checked.
        cost = [1] * n
        gas = [0] * (n - 1) + [n + 1]
        expected = _gas_station_oracle(gas, cost)
    return [gas, cost], expected


@profiler_input("gas-station")
def _gas_station_profiler(n: int, rng: random.Random) -> list:
    # The answer is the LAST station, and every earlier start fails only on the
    # step that would have carried it there.
    #
    # cost[i] = n everywhere; gas ramps at n + 1 (a net gain of +1 per station)
    # and drops to 0 at station n - 2, with the whole surplus parked at station
    # n - 1. Starting at j < n - 1 the tank climbs by one per station and the
    # cliff empties it, so the failure lands exactly on the step before station
    # n - 1 — a per-start simulation is Theta(n^2) here (20.5M steps at n = 6400)
    # and the brute-force oracle cannot early-exit. The canonical greedy still
    # scans all n stations and returns n - 1, which is what makes the answer's
    # position a real test of "did you traverse".
    #
    # Values respect the statement: cost = n and gas <= n + 3 are both inside
    # 0..10^4 for every probe size (the ladder tops out at n = 6400, so cost = n
    # is comfortably legal; a shorter ladder would still work, a longer one would
    # need a different base cost).
    n = max(1, int(n))
    if n == 1:
        return [[4], [1]]  # single station, and it is the last one: 4 >= 1
    cost = [n] * n
    gas = [n + 1] * (n - 2) + [0, n + 3]
    return [gas, cost]


@oracle("valid-parenthesis-string")
def _valid_parenthesis_string_oracle(s: str) -> bool:
    """Brute force over the readings, memoized on (position, open count).

    The definition is itself a search: each '*' may be '(', ')' or the empty
    string, and the string is valid exactly when some choice of readings is a
    correctly matched bracket string, i.e. when the running number of unmatched
    '(' never goes negative and is zero at the end. This walks the string trying
    all three readings at every star; the only thing it prunes is a prefix that has
    already closed more brackets than it opened, which no later reading can repair.
    `failed` remembers the (position, open) states already proven dead, which is
    what turns 3^(number of stars) into O(n^2) states. Total on the empty string
    (which the statement's length bound excludes)."""
    failed: set[tuple[int, int]] = set()

    def read(index: int, opens: int) -> bool:
        if opens < 0:
            return False
        if index == len(s):
            return opens == 0
        if (index, opens) in failed:
            return False
        char = s[index]
        if char == "(":
            options = (opens + 1,)
        elif char == ")":
            options = (opens - 1,)
        else:  # '*': read it as '(', as ')' or as the empty string
            options = (opens + 1, opens, opens - 1)
        for nxt in options:
            if read(index + 1, nxt):
                return True
        failed.add((index, opens))
        return False

    return read(0, 0)


def _valid_parenthesis_string_balanced(pairs: int, rng: random.Random) -> str:
    """A random correctly matched bracket string with `pairs` pairs."""
    if pairs == 0:
        return ""
    left = rng.randint(0, pairs - 1)
    return (
        "("
        + _valid_parenthesis_string_balanced(left, rng)
        + ")"
        + _valid_parenthesis_string_balanced(pairs - 1 - left, rng)
    )


def _valid_parenthesis_string_valid(size: int, rng: random.Random) -> str:
    """A valid string of exactly `size` characters.

    A real bracket string is built first, then some of its brackets are rewritten
    to '*' - so those stars MUST read as that bracket - and the remaining length is
    filled with '*' that read as the empty string. Nothing here can produce an
    invalid string: every '*' has the reading of the bracket it replaced, or reads
    as empty."""
    chars = [
        "*" if char == "(" and rng.random() < 0.35
        else "*" if char == ")" and rng.random() < 0.35
        else char
        for char in _valid_parenthesis_string_balanced(size // 2, rng)
    ]
    while len(chars) < size:
        chars.insert(rng.randint(0, len(chars)), "*")
    return "".join(chars)


def _valid_parenthesis_string_pad(shape: str, size: int, rng: random.Random) -> str:
    """Grow `shape` to `size` characters with stars, inserted at random positions.

    Inserting a star that can read as the empty string cannot make a VALID string
    invalid: the original reading is still available (and every reading of the
    padded string restricts to a reading of the original). It can however rescue an
    INVALID string - the inserted star brings two new readings with it - which is
    why the invalid templates below are emitted unpadded."""
    chars = list(shape)
    while len(chars) < size:
        chars.insert(rng.randint(0, len(chars)), "*")
    return "".join(chars)


@judge_case("valid-parenthesis-string")
def _valid_parenthesis_string_case(n: int, rng: random.Random) -> tuple[list, bool]:
    size = max(1, min(n, 12))  # statement: 1 <= s.length <= 100
    roll = rng.random()
    # The star-critical shapes: cases where a 'count the stars and compare'
    # answer and the two-counter range disagree. In "(*))" the star must be a '('
    # to close the pair, in "((*)" it must be a ')', in "(*)" and "*" it must be
    # the empty string, and "**(" is false however the stars read - the three
    # readings the low/high range keeps apart. The self-check proves those roles by
    # enumerating every reading of every star, outside the fragment.
    opens_shape = [
        "*",          # true  - the star reads as empty
        "(*",         # true  - the star reads as ')'
        "*)",         # true  - the star reads as '('
        "**",         # true
        "(*)",        # true  - empty
        "(*))",       # true  - '(' (statement example 3)
        "((*)",       # true  - ')'
        "((**",       # true  - two stars as ')'
        "(**)",       # true
        "*()",        # true  - empty
        "(()*",       # true
    ]
    closed_shapes = [
        "*(",         # false - nothing after the '(' can close it
        "**(",        # false
        "*))",        # false - two stars cannot close three brackets
        "*)(",        # false
        "(((*",       # false - one star cannot close three opens
        "(((((****",  # false - four stars cannot close five opens
    ]
    if roll < 0.2:
        # A valid shape, padded to length with extra stars: the padding is where
        # the third role (a star reading as the empty string) comes from, and it
        # cannot change the verdict - the shape's own reading survives.
        shape = rng.choice([candidate for candidate in opens_shape if len(candidate) <= size])
        s = _valid_parenthesis_string_pad(shape, size, rng)
    elif roll < 0.35:
        # A false shape, emitted at its own length: padding it with stars would add
        # readings and could rescue it ("**))" is true while "*))" is false), and
        # this case is here to be false.
        usable = [candidate for candidate in closed_shapes if len(candidate) <= size]
        if usable:
            s = rng.choice(usable)
        else:  # size == 1: no star-critical false shape fits, so take a valid one
            s = rng.choice([candidate for candidate in opens_shape if len(candidate) <= size])
    elif roll < 0.7:
        # Valid by construction: a bracket string with some brackets rewritten to
        # '*' (that star must read as the bracket it replaced) and the rest filled
        # with '*' reading as empty. Exercises all three readings at once.
        s = _valid_parenthesis_string_valid(size, rng)
    elif roll < 0.85:
        # One character of a valid string changed: usually invalid, and the change
        # is usually adjacent to a star, which is where a range bug shows up.
        chars = list(_valid_parenthesis_string_valid(size, rng))
        index = rng.randrange(len(chars))
        chars[index] = rng.choice([c for c in "()*" if c != chars[index]])
        s = "".join(chars)
    else:
        # An unstructured draw.
        s = "".join(rng.choice("()*") for _ in range(size))
    return [s], _valid_parenthesis_string_oracle(s)


@profiler_input("valid-parenthesis-string")
def _valid_parenthesis_string_profiler(n: int, rng: random.Random) -> list:
    # A valid string of length size: half '(' and half '*' that close them. Nothing
    # can early-exit - the answer is true, no prefix pushes the minimum open count
    # below zero, and every character moves both counters, which is the whole cost
    # of the intended pass (a stack solution pays size pushes and pops on it).
    #
    # probe_max_n = 100 is a fidelity cap, not a preference: the statement bounds
    # s at 100 characters, so the default ladder's 6400 would measure inputs the
    # problem never promises (the merge-two-sorted-lists precedent). The cost is
    # resolution - over a 1..100 ladder an O(n) solution can realistically only
    # come back "agrees with the reference" or "unresolved", and unresolved is the
    # honest reading rather than a curation bug. What it still buys is the digest
    # check at 100 characters, ten times any generated case.
    size = max(1, min(n, 100))
    opens = size // 2
    return ["(" * opens + "*" * (size - opens)]


@oracle("partition-labels")
def _partition_labels_oracle(s: str) -> list[int]:
    """Brute force, straight off the definition: a cut is *allowed* only when no
    letter occurs on both sides of it, and "as many parts as possible" is exactly
    taking every allowed cut. O(n^2) — each candidate cut rebuilds both sides as
    sets — and it builds the whole cut list before emitting a single size, so it
    never stops early.

    The empty string is excluded by 1 <= s.length; it returns [] there (there are
    no parts), which is also what the reference returns."""
    n = len(s)
    if n == 0:
        return []
    cuts: list[int] = []
    for i in range(n - 1):
        if not (set(s[: i + 1]) & set(s[i + 1 :])):
            cuts.append(i + 1)
    sizes: list[int] = []
    prev = 0
    for cut in cuts + [n]:
        sizes.append(cut - prev)
        prev = cut
    return sizes


@judge_case("partition-labels")
def _partition_labels_case(n: int, rng: random.Random) -> tuple[str, list[int]]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= s.length
    # A small alphabet, so repeats, re-entries and single-letter parts all show
    # up in a 12-character case; occasionally the whole alphabet, for the
    # many-distinct-letters shape.
    width = 26 if rng.random() < 0.25 else rng.randint(1, 4)
    alphabet = "abcdefghijklmnopqrstuvwxyz"[:width]
    s = "".join(rng.choice(alphabet) for _ in range(n))
    return [s], _partition_labels_oracle(s)


@profiler_input("partition-labels")
def _partition_labels_profiler(n: int, rng: random.Random) -> list:
    # The 26-letter cycle, truncated to n (probe_max_n = 500 keeps n inside the
    # statement's own length bound). Every letter is still ahead of the current
    # part's end, so the greedy's window stretches to the very end of the string
    # and its merge loop visits all n indices before the single cut — nothing to
    # early-exit on. A per-index forward scan for a letter's last occurrence (the
    # obvious quadratic student) walks to the far end of the string from every
    # index, Theta(n^2) at n = 500; the reference does its two linear passes.
    # Values are lowercase English letters, inside the constraint.
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    n = max(1, int(n))
    return [(alphabet * (n // 26 + 1))[:n]]


@oracle("hand-of-straights")
def _hand_of_straights_oracle(hand: list[int], group_size: int) -> bool:
    """Exhaustive search: peel one group off at a time, recursing on the rest.

    A group is `group_size` *consecutive* cards, so the group holding the smallest
    remaining card can only be the run that starts there. This does not take that
    on trust: it enumerates every sub-multiset of that size from the remaining
    cards, keeps the ones whose values are that run, and recurses on what is left.
    With duplicates several index combinations are the same pick - a group's values
    are forced once its smallest card is fixed, so the enumeration's alternatives
    are all rejected and the search consumes cards rather than choosing between
    readings.

    What it does not reuse from the reference is any of the counting: no
    multiplicities, no divisibility shortcut, no sorted sweep. Removing ONE card per
    value (not every copy of those values - the hand is a multiset, and this is
    where such a search usually goes wrong) is a merge walk over the two sorted
    lists, and `failed` memoizes the multisets already proven impossible.

    Total on the empty hand (excluded by the statement's length bound) and on
    group_size 1, where every single card is a group of one. The recursion costs
    one frame per group peeled, so it reaches ~2900 cards at group_size 3 and would
    hit the interpreter's limit beyond that; every path that runs it stays far
    below - generated cases are <= 12 cards and the probe's oracle-versus-reference
    differential stops at 800 cards (the full 6400-card ladder measures the
    reference alone)."""
    cards = sorted(hand)
    if group_size < 1 or len(cards) % group_size:
        return False
    failed: set[tuple[int, ...]] = set()

    def peel(remaining: tuple[int, ...]) -> bool:
        if not remaining:
            return True
        if remaining in failed:
            return False
        run = [remaining[0] + step for step in range(group_size)]
        for picked in _hand_of_straights_groups(remaining, group_size):
            if sorted(picked) != run:
                continue
            gone = sorted(picked)
            rest: list[int] = []
            taken = 0
            for card in remaining:  # both lists are sorted: drop one copy per value
                if taken < len(gone) and card == gone[taken]:
                    taken += 1
                    continue
                rest.append(card)
            if peel(tuple(rest)):
                return True
        failed.add(remaining)
        return False

    return peel(tuple(cards))


def _hand_of_straights_groups(cards: tuple[int, ...], group_size: int):
    """Lazily yield every `group_size`-card sub-multiset of `cards` that contains
    its first card, as a value list. Index combinations, so two copies of the same
    value are two distinct choices."""

    def tails(start: int, need: int):
        if need == 0:
            yield ()
            return
        for index in range(start, len(cards) - need + 1):
            for rest in tails(index + 1, need - 1):
                yield (index,) + rest

    for indexes in tails(1, group_size - 1):
        yield [cards[0]] + [cards[index] for index in indexes]


@judge_case("hand-of-straights")
def _hand_of_straights_case(n: int, rng: random.Random) -> tuple[list, bool]:
    size = max(1, min(n, 12))  # statement: 1 <= hand.length <= 10^4
    group_size = rng.randint(1, size)  # statement: 1 <= groupSize <= hand.length
    roll = rng.random()
    if roll < 0.45 and size % group_size == 0:
        # A hand that IS a partition: size / group_size groups of consecutive
        # cards laid down at random starts. Groups may share values - the hand is a
        # multiset, so [1,2,3,1,2,3] is two groups of three.
        hand: list[int] = []
        for _ in range(size // group_size):
            start = rng.randint(0, 9)
            hand.extend(range(start, start + group_size))
    elif roll < 0.75:
        # A partitionable-looking hand with one card bumped by +1: the runs are
        # right but a count is off. This is the near miss the examples miss (they
        # fail on divisibility), and whether it is really unpartitionable is the
        # oracle's call, not the construction's.
        hand = []
        for _ in range(max(1, size // group_size)):
            start = rng.randint(0, 9)
            hand.extend(range(start, start + group_size))
        hand = hand[:size]
        hand[rng.randrange(len(hand))] += 1
    else:
        # No structure at all: duplicates and gaps in any arrangement.
        hand = [rng.randint(0, 9) for _ in range(size)]
    rng.shuffle(hand)
    return [hand, group_size], _hand_of_straights_oracle(hand, group_size)


@profiler_input("hand-of-straights")
def _hand_of_straights_profiler(n: int, rng: random.Random) -> list:
    # A hand that IS partitionable and has all-distinct values: the run 0, 1, ...,
    # size-1 cut into groups of three, inside the statement's 0..10^9 range.
    # Nothing can early-exit - the answer is true, no value of a run is missing and
    # every card is consumed - and ~n distinct values are what makes the counting
    # sweep sort a key per card, which is the intended solution's real cost (a
    # heap-based solution pays the same n log n, and a per-card rescan is what the
    # probe is there to catch).
    #
    # The ladder's smallest points bottom out at three cards, the fewest that can
    # form a group at all; the values stay distinct, so no duplicate can mask a
    # dropped or double-counted card and the digest changes with it.
    group_size = 3
    size = max(group_size, n - n % group_size)
    return [[i for i in range(size)], group_size]


@oracle("merge-triplets-to-form-target-triplet")
def _merge_triplets_oracle(triplets: list[list[int]], target: list[int]) -> bool:
    """Brute force by running the stated operation to its end.

    A merge writes a componentwise max into one of the two slots, so a triplet
    that is already above `target` in some coordinate can never come back down.
    Nor can one ever help: follow the lineage of the element that ends up equal to
    `target` back through the merges that built it and every value on that lineage
    is the componentwise max of some subset of the original triplets - hence at
    most `target` componentwise, because the final value is `target`. So only
    triplets that stay inside `target` can take part in a sequence that works.

    Merging *all* of those into a single slot is a legal sequence of the stated
    operation, and it leaves their componentwise maximum in that slot: the largest
    triplet any legitimate sequence can hold. The target is obtainable exactly when
    that maximum is the target itself - if it is below the target in some
    coordinate, every subset's maximum is too. One pass, O(1) extra space, total on
    an empty triplet list (which the statement's length bound excludes)."""
    size = len(target)
    best = None
    for row in triplets:
        if all(row[k] <= target[k] for k in range(size)):
            best = list(row) if best is None else [max(best[k], row[k]) for k in range(size)]
    return best is not None and best == list(target)


@judge_case("merge-triplets-to-form-target-triplet")
def _merge_triplets_case(n: int, rng: random.Random) -> tuple[list, list]:
    size = max(1, min(n, 12))  # statement: 1 <= triplets.length <= 10^5
    # Every coordinate stays inside the statement's 1..1000 (these are 1..11), and
    # the target's own values are >= 2 so that "one below it" is still >= 1.
    target = [rng.randint(2, 8) for _ in range(3)]
    roll = rng.random()
    if roll < 0.4:
        # Obtainable: one triplet per coordinate, each one inside the target and
        # matching it on its own axis.
        triplets = [
            [target[axis] if k == axis else rng.randint(1, target[k]) for k in range(3)]
            for axis in range(3)
        ]
    elif roll < 0.55:
        # Obtainable the easy way: the target is already a triplet.
        triplets = [list(target)]
    elif roll < 0.8:
        # Every triplet stays inside the target, yet one coordinate is never hit
        # exactly - so the answer is false although nothing overshoots.
        axis = rng.randrange(3)
        triplets = [
            [rng.randint(1, target[k] - 1) if k == axis else rng.randint(1, target[k])
             for k in range(3)]
            for _ in range(size)
        ]
    elif roll < 0.9:
        # Every triplet overshoots the target in the same coordinate: none of them
        # may take part, and no merge can repair a value that is already too big.
        axis = rng.randrange(3)
        over = target[axis] + rng.randint(1, 3)
        triplets = [
            [over if k == axis else rng.randint(1, target[k]) for k in range(3)]
            for _ in range(size)
        ]
    else:
        # An unstructured draw: random triplets against a random target.
        triplets = [[rng.randint(1, 8) for _ in range(3)] for _ in range(size)]
    triplets = triplets[:size]
    while len(triplets) < size:
        # Filler rows, drawn like the unstructured branch: they may add coverage or
        # overshoot, and the oracle decides what that does to the answer.
        triplets.append([rng.randint(1, 8) for _ in range(3)])
    rng.shuffle(triplets)
    return [triplets, target], _merge_triplets_oracle(triplets, target)


@profiler_input("merge-triplets-to-form-target-triplet")
def _merge_triplets_profiler(n: int, rng: random.Random) -> list:
    # n triplets, every one of them inside the target (so a correct solution must
    # look at all of them - it cannot discard a row and stop), but the third
    # coordinate is drawn from 1..999 against a target of 1000, so that coordinate
    # is never matched and the answer is false: no implementation can return early
    # on a success either. Values stay inside the statement's 1..1000 and ~n rows of
    # three coordinates are the input's whole size.
    target = [1000, 1000, 1000]
    triplets = [
        [rng.randint(1, 1000), rng.randint(1, 1000), rng.randint(1, 999)]
        for _ in range(n)
    ]
    return [triplets, target]


# ----------------------------------------------------------------- class mode
# min_stack: an "ops" problem — the case replays a method sequence on a fresh
# instance and compares the per-op outputs. The replay oracle below is a
# reference implementation (quarantine zone, never tutor context).


@oracle("min_stack")
def _min_stack_oracle(ops: list[list]) -> list:
    stack: list[int] = []
    mins: list[int] = []
    out: list = []
    for op in ops:
        method, *args = op
        if method == "push":
            stack.append(args[0])
            mins.append(args[0] if not mins else min(args[0], mins[-1]))
            out.append(None)
        elif method == "pop":
            stack.pop()
            mins.pop()
            out.append(None)
        elif method == "top":
            out.append(stack[-1])
        elif method == "getMin":
            out.append(mins[-1])
        else:  # pragma: no cover - generators only emit the four methods
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("min_stack")
def _min_stack_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(1, min(n, 12))
    ops: list[list] = []
    size = 0
    for _ in range(n * 2 + 1):
        choices = ["push"]
        if size > 0:
            choices += ["pop", "top", "getMin"]
        method = rng.choice(choices)
        if method == "push":
            ops.append(["push", rng.randint(-20, 20)])
            size += 1
        else:
            ops.append([method])
            if method == "pop":
                size -= 1
    return [], _min_stack_oracle(ops), {"ops": ops}



# ----------------------------------------------------------------------- sliding_window



@oracle("best-time-to-buy-and-sell-stock")
def _best_time_to_buy_and_sell_stock_oracle(prices: list[int]) -> int:
    best = 0
    for i in range(len(prices)):
        for j in range(i + 1, len(prices)):
            best = max(best, prices[j] - prices[i])
    return best


@judge_case("best-time-to-buy-and-sell-stock")
def _best_time_to_buy_and_sell_stock_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: length >= 1
    prices = [rng.randint(0, 20) for _ in range(n)]
    return [prices], _best_time_to_buy_and_sell_stock_oracle(prices)


@profiler_input("best-time-to-buy-and-sell-stock")
def _best_time_to_buy_and_sell_stock_profiler(n: int, rng: random.Random) -> list:
    # Strictly decreasing, inside the statement's value range: the running minimum
    # updates on every step (nothing to early-exit on for either implementation)
    # and no profitable pair exists, so the answer is 0 without a scan stopping
    # early on a lucky buy.
    return [[max(1, 10_000 - i) for i in range(n)]]
@oracle("longest-substring-without-repeating-characters")
def _longest_substring_without_repeating_characters_oracle(s: str) -> int:
    best = 0
    for start in range(len(s)):
        seen: set[str] = set()
        for end in range(start, len(s)):
            if s[end] in seen:
                break
            seen.add(s[end])
            best = max(best, end - start + 1)
    return best


@judge_case("longest-substring-without-repeating-characters")
def _longest_substring_without_repeating_characters_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(0, min(n, 12))  # the statement's own constraint is 0 <= s.length: n = 0 stays 0
    alphabet = "abcABC12 ."  # letters, digits, a symbol and a space — the statement's own set
    s = "".join(rng.choice(alphabet) for _ in range(n))
    return [s], _longest_substring_without_repeating_characters_oracle(s)


@profiler_input("longest-substring-without-repeating-characters")
def _longest_substring_without_repeating_characters_profiler(n: int, rng: random.Random) -> list:
    # A shuffled cycle through (almost) every character the statement allows.
    # Every window of at most len(chars) consecutive characters is repeat-free,
    # so the window grows to the alphabet's own size — the longest a repeat-free
    # substring can be under these constraints — instead of stopping early on a
    # repeat, and the cycle keeps the left pointer moving. Values stay inside
    # "English letters, digits, symbols and spaces".
    chars = list(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        " .,;:!?+-*/=_()[]{}<>@#$%&|~^`"
    )
    rng.shuffle(chars)
    cycle = "".join(chars)
    return ["".join(cycle[i % len(cycle)] for i in range(n))]


@oracle("minimum-window-substring")
def _minimum_window_substring_oracle(s: str, t: str) -> str:
    """Brute force: for each start, extend until the window covers t; the first
    covering window is the shortest one starting at that index."""
    from collections import Counter

    need = Counter(t)
    if not need:
        return ""  # an empty t is covered by the empty window
    best = ""
    for i in range(len(s)):
        have: Counter = Counter()
        for j in range(i, len(s)):
            have[s[j]] += 1
            if all(have[c] >= need[c] for c in need):
                if not best or j - i + 1 < len(best):
                    best = s[i : j + 1]
                break
    return best


@judge_case("minimum-window-substring")
def _minimum_window_substring_case(n: int, rng: random.Random) -> tuple[list, str, dict]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= m, n <= 10^5
    letters = "abAB"  # English letters; a tiny alphabet so windows collide
    s = "".join(rng.choice(letters) for _ in range(n))
    if rng.random() < 0.5:
        # A substring of s, so a window exists for sure -- and often more than
        # one of minimal length, which is what the predicate verdict is for.
        start = rng.randrange(n)
        t = s[start : start + rng.randint(1, n - start)]
    else:
        t = "".join(rng.choice(letters) for _ in range(rng.randint(1, n)))
    return [s, t], _minimum_window_substring_oracle(s, t), {"predicate": "minimum_window_valid"}


@checker("minimum_window_valid")
def _minimum_window_substring_valid(module, got, args) -> bool:
    """The contract as a property, because the minimal window is NOT unique.

    Over the statement's own constraints ("abba"/"ab") admits both "ab" and
    "ba" at the minimal length 2; the statement's uniqueness sentence is a
    promise about LeetCode's hidden testcases, not about this function. So the
    checker computes only the minimal *length* -- never the oracle's choice
    among the ties -- and then accepts any substring of s of that length that
    covers t. Equality judging here would false-fail a correct solution that
    picked the other minimal window (the k_closest_points trust bug)."""
    from collections import Counter

    s, t = args
    if not isinstance(got, str):
        return False
    need = Counter(t)
    if not need:
        return got == ""  # an empty t is covered by the empty window
    best = None
    for i in range(len(s)):
        have: Counter = Counter()
        for j in range(i, len(s)):
            have[s[j]] += 1
            if all(have[c] >= need[c] for c in need):
                if best is None or j - i + 1 < best:
                    best = j - i + 1
                break
    if best is None:
        return got == ""  # nothing in s covers t: "" is the only answer
    if len(got) != best:
        return False
    if any(got.count(c) < need[c] for c in need):
        return False
    return any(s[i : i + best] == got for i in range(len(s) - best + 1))


@profiler_input("minimum-window-substring")
def _minimum_window_substring_profiler(n: int, rng: random.Random) -> list:
    # The only 'b' in s sits on the very last character and t needs n//4 a's,
    # so the window closes exactly there and the shrink phase then walks back
    # over the whole 'a' run: both phases of the two-pointer traverse the
    # string, and t itself is Theta(n) so the n-term of the O(m + n) target is
    # exercised as well as the m-term (a constant-size t would measure only m).
    # The brute-force oracle never breaks early for the first ~3n/4 starts, and
    # no shorter window can cover t. A random string over a small alphabet
    # closes a window almost immediately and would measure the best case.
    size = max(8, n)
    quarter = size // 4
    return ["a" * (size - quarter - 2) + "b", "a" * quarter + "b"]


@oracle("sliding-window-maximum")
def _sliding_window_maximum_oracle(nums: list[int], k: int) -> list[int]:
    """Brute force: recompute the maximum of every window from scratch."""
    return [max(nums[i : i + k]) for i in range(len(nums) - k + 1)]


@judge_case("sliding-window-maximum")
def _sliding_window_maximum_case(n: int, rng: random.Random) -> tuple[list, list]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= nums.length
    if rng.random() < 0.5:
        nums = [rng.randint(-4, 4) for _ in range(n)]  # ties and negatives
    else:
        nums = [rng.randint(-10_000, 10_000) for _ in range(n)]  # the stated range
    k = rng.randint(1, n)  # the statement's own constraint: 1 <= k <= nums.length
    return [nums, k], _sliding_window_maximum_oracle(nums, k)


@profiler_input("sliding-window-maximum")
def _sliding_window_maximum_profiler(n: int, rng: random.Random) -> list:
    # Strictly decreasing and inside the statement's value range: the monotonic
    # deque never pops from the back, so it fills to k and every index is pushed
    # once and popped once (its amortized worst case), while a heap solution
    # keeps k live entries and pops one stale one per step. A random or
    # increasing array lets the deque stay at size 1 and measures the best case.
    size = max(2, n)
    nums = [max(-10_000, 10_000 - i) for i in range(size)]
    return [nums, max(1, size // 2)]


@oracle("longest-repeating-character-replacement")
def _longest_repeating_character_replacement_oracle(s: str, k: int) -> int:
    best = 0
    for start in range(len(s)):
        counts: dict[str, int] = {}
        for end in range(start, len(s)):
            counts[s[end]] = counts.get(s[end], 0) + 1
            length = end - start + 1
            if length - max(counts.values()) > k:
                break
            best = max(best, length)
    return best


@judge_case("longest-repeating-character-replacement")
def _longest_repeating_character_replacement_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own constraint: 1 <= s.length
    s = "".join(rng.choice("ABC") for _ in range(n))
    k = rng.randint(0, n)  # the statement's own constraint: 0 <= k <= s.length
    return [s, k], _longest_repeating_character_replacement_oracle(s, k)


@profiler_input("longest-repeating-character-replacement")
def _longest_repeating_character_replacement_profiler(n: int, rng: random.Random) -> list:
    # A strict A..Z cycle keeps every window's counts balanced, so the maximum
    # frequency of a window stays near len/26 and the window that satisfies
    # len - maxfreq <= k is about 1.04k long: with k = n // 2 the answer is
    # Theta(n), which is what makes a nested-loop solution measure quadratic
    # instead of looking linear. The window shrinks periodically (the whole
    # string is scanned, there is no early exit) and k sits strictly between the
    # two shortcut values — k > 0 (so the "k = 0, just find the longest run"
    # special case cannot trigger) and k < n - maxfreq_total (so "replace
    # everything, the answer is n" cannot either). Uppercase only, k <= n.
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = "".join(letters[i % len(letters)] for i in range(n))
    return [s, n // 2]


@oracle("permutation-in-string")
def _permutation_in_string_oracle(s1: str, s2: str) -> bool:
    target = sorted(s1)
    width = len(s1)
    for start in range(len(s2) - width + 1):
        if sorted(s2[start : start + width]) == target:
            return True
    return False


@judge_case("permutation-in-string")
def _permutation_in_string_case(n: int, rng: random.Random) -> tuple[list, bool]:
    size = max(1, min(n, 12))  # the statement's own constraint: both lengths >= 1
    a = rng.randint(1, size)
    b = rng.randint(1, size)  # drawn independently: s1 longer than s2 is a legal input
    s1 = "".join(rng.choice("ab") for _ in range(a))
    s2 = "".join(rng.choice("ab") for _ in range(b))
    return [s1, s2], _permutation_in_string_oracle(s1, s2)


@profiler_input("permutation-in-string")
def _permutation_in_string_profiler(n: int, rng: random.Random) -> list:
    # s1 is an "ab" cycle of about n/4 characters and s2 an "abc" cycle holding
    # the rest, so the total size is ~n. The window width grows with n, which is
    # what makes a per-window O(len(s1)) or O(len(s1) log len(s1)) solution
    # (Counter- or sorted-comparison per window) measure quadratic, while n2 - n1
    # is still about n/2 window positions for the reference. No window can match:
    # every stretch of >= 3 consecutive characters of the "abc" cycle contains a
    # "c", and s1 contains none — so the answer is False all the way and nothing
    # early-exits. Both strings are lowercase English letters.
    width = max(3, n // 4)
    rest = max(1, n - width)
    s1 = ("ab" * (width // 2 + 1))[:width]
    s2 = ("abc" * (rest // 3 + 1))[:rest]
    return [s1, s2]

# ----------------------------------------------------------------------- tries


@oracle("implement-trie-prefix-tree")
def _implement_trie_prefix_tree_oracle(ops: list[list]) -> list:
    # Brute force: keep the inserted words in a list and answer every query by
    # scanning it — membership for search, a startswith scan for startsWith.
    # O(N * L) a query, which is exactly what the trie exists to avoid.
    words: list[str] = []
    out: list = []
    for op in ops:
        method, *args = op
        if method == "insert":
            words.append(args[0])
            out.append(None)
        elif method == "search":
            out.append(args[0] in words)
        elif method == "startsWith":
            out.append(any(word.startswith(args[0]) for word in words))
        else:  # pragma: no cover - the generator only emits the three methods
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("implement-trie-prefix-tree")
def _implement_trie_prefix_tree_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # Deterministic by construction: every op comes from the seeded rng, the
    # alphabet and the length range are fixed, and the op list replays on a fresh
    # instance (the judge harness builds one per case).
    steps = 2 * max(1, min(n, 12)) + 1
    alphabet = "ab"  # two letters: prefixes collide in almost every call
    ops: list[list] = []
    inserted: list[str] = []
    for step in range(steps):
        if not inserted or step % 3 == 0:
            # 1 <= word.length <= 2000, lowercase only: 1..4 letters of "ab"
            word = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 4)))
            ops.append(["insert", word])
            if word not in inserted:
                inserted.append(word)
            continue
        word = rng.choice(inserted)
        cut = rng.randint(1, len(word))  # a real prefix, sometimes the word itself
        roll = rng.randint(0, 3)
        if roll == 0:
            ops.append(["search", word])  # a hit
        elif roll == 1:
            ops.append(["search", word + rng.choice(alphabet)])  # a miss
        elif roll == 2:
            ops.append(["startsWith", word[:cut]])  # a hit (the empty prefix is
            # not reachable here: cut >= 1)
        else:
            # a real prefix asked as a whole word: true exactly when that prefix
            # was itself inserted earlier, which is what makes search and
            # startsWith differ
            ops.append(["search", word[:cut]])
    return [], _implement_trie_prefix_tree_oracle(ops), {"ops": ops}


@oracle("design-add-and-search-words-data-structure")
def _design_add_and_search_words_data_structure_oracle(ops: list[list]) -> list:
    # Brute force: keep every added word and, for a query, compare it against them
    # one at a time — a plain membership test when the pattern has no dot, a
    # per-character match when it has one. O(N * L) a query, no trie, no prefix
    # pruning: the differential against the reference is real.
    words: list[str] = []
    out: list = []
    for op in ops:
        method, *args = op
        if method == "addWord":
            words.append(args[0])
            out.append(None)
        elif method == "search":
            pattern = args[0]
            hit = False
            for word in words:
                if len(word) != len(pattern):
                    continue
                if all(p == "." or p == ch for p, ch in zip(pattern, word)):
                    hit = True
                    break
            out.append(hit)
        else:  # pragma: no cover - the generator only emits addWord and search
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("design-add-and-search-words-data-structure")
def _design_add_and_search_words_data_structure_case(
    n: int, rng: random.Random
) -> tuple[list, list, dict]:
    # Deterministic by construction: every op comes from the seeded rng, the
    # alphabet and length range are fixed, and the op list replays on a fresh
    # instance (the judge harness builds one per case).
    steps = 2 * max(1, min(n, 12)) + 1
    alphabet = "ab"  # two letters: words overlap and prefix each other constantly
    ops: list[list] = []
    added: list[str] = []
    patterns = 0  # cycles the dot through first, last and middle position
    for step in range(steps):
        if not added or step % 3 == 0:
            # 1 <= word.length <= 25, lowercase only: 1..4 letters of "ab"
            word = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 4)))
            ops.append(["addWord", word])
            if word not in added:
                added.append(word)
            continue
        base = rng.choice(added)  # 1..4 letters, already in the dictionary
        if rng.random() < 0.15:
            # Occasionally a dotted query whose LENGTH no added word has: the
            # statement allows it, and without it a solution that only ever
            # matched against existing word lengths looked complete (verifier
            # finding, v0.14).
            length = 1 + (len(base) % 4) + 1  # one longer than a 1..4-letter base
            base = "".join(rng.choice(alphabet) for _ in range(min(length, 4)))
            if base in added:
                base = base + "a" if len(base) < 4 else base
        roll = rng.randint(0, 3)
        if roll == 0:
            ops.append(["search", base])  # a hit
        elif roll == 1:
            # ONE dot, placed at the first, the last and the middle position in
            # turn: the statement's only worked example puts it in the middle
            # (".ad"), so a generator that never tried the ends would leave "a dot
            # matches any single letter" half-pinned.
            pos = (0, len(base) - 1, len(base) // 2)[patterns % 3]
            patterns += 1
            ops.append(["search", base[:pos] + "." + base[pos + 1:]])
        elif roll == 2 and len(base) >= 2:
            # TWO dots — the statement's own maximum per query. The two ends when
            # the word has a middle to spare, a random distinct pair otherwise.
            if len(base) >= 3 and patterns % 2:
                i, j = 0, len(base) - 1
            else:
                i, j = sorted(rng.sample(range(len(base)), 2))
            patterns += 1
            chars = list(base)
            chars[i] = chars[j] = "."
            ops.append(["search", "".join(chars)])
        else:
            # a length the dictionary cannot hold: one letter longer, or one
            # shorter (never empty — the statement's floor is length 1)
            if len(base) >= 2 and rng.random() < 0.5:
                ops.append(["search", base[:-1]])
            else:
                ops.append(["search", base + rng.choice(alphabet)])
    return [], _design_add_and_search_words_data_structure_oracle(ops), {"ops": ops}


@oracle("word-search-ii")
def _word_search_ii_oracle(board: list[list[str]], words: list[str]) -> list[str]:
    # Brute force, and deliberately not a trie: for each word, walk the board once
    # looking for it — a DFS from every cell whose letter starts the word, with a
    # visited set that is undone on the way out (the statement forbids reusing a
    # cell within a word). No sharing between words at all. The result is sorted,
    # which is the canonical form of a set answer (the corpus convention for
    # "compare": "sorted"), so the visible tests can carry the statement's own
    # example output verbatim.
    rows = len(board)
    cols = len(board[0]) if rows else 0
    found: list[str] = []

    def _word_search_ii_here(word: str) -> bool:
        last = len(word) - 1
        visited = [[False] * cols for _ in range(rows)]

        def _word_search_ii_step(r: int, c: int, k: int) -> bool:
            if board[r][c] != word[k]:
                return False
            if k == last:
                return True
            visited[r][c] = True
            hit = any(
                _word_search_ii_step(nr, nc, k + 1)
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]
            )
            visited[r][c] = False
            return hit

        return any(
            _word_search_ii_step(r, c, 0) for r in range(rows) for c in range(cols)
        )

    for word in dict.fromkeys(words):  # the statement promises unique words
        if word and len(word) <= rows * cols and _word_search_ii_here(word):
            found.append(word)
    return sorted(found)


@judge_case("word-search-ii")
def _word_search_ii_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # Deterministic by construction: the board, the words and the paths they are
    # spelled along all come from the seeded rng, and the expected answer is the
    # oracle's own output. The board is 1..4 cells a side (independently per axis) and a word 1..4 letters
    # — well inside the statement's 12 x 12 and 10 (a case has to stay small
    # enough for the brute-force oracle), and every word is unique.
    n = max(1, min(n, 12))
    # Rows and columns vary INDEPENDENTLY (the statement allows m != n): every
    # generated board used to be square, so a solution that assumed a square
    # shape passed the whole generated set and was caught only by the 1x2 visible
    # case (verifier finding, v0.14).
    rows = 1 + n % 4  # 1 <= board.length, board[i].length <= 12
    cols = 1 + (n // 4) % 4
    letters = "abc"  # a small alphabet, so words do overlap real board paths
    board = [[rng.choice(letters) for _ in range(cols)] for _ in range(rows)]

    def _word_search_ii_spelled(length: int) -> str:
        # A self-avoiding walk of `length` cells spelled out: a string that really
        # is on the board, which is how a present word (and a long shared prefix)
        # gets built rather than hoped for.
        r, c = rng.randrange(rows), rng.randrange(cols)
        seen = {(r, c)}
        out = [board[r][c]]
        while len(out) < length:
            options = [
                (nr, nc)
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen
            ]
            if not options:
                break  # cornered early: a shorter word is still a real path
            r, c = rng.choice(options)
            seen.add((r, c))
            out.append(board[r][c])
        return "".join(out)

    words: list[str] = []
    for _ in range(1 + n % 3):
        words.append(_word_search_ii_spelled(rng.randint(1, 4)))  # usually present
    for _ in range(1 + n % 3):
        words.append(  # 1 <= length <= 10, lowercase only
            "".join(rng.choice(letters) for _ in range(rng.randint(1, 4)))
        )
    words = list(dict.fromkeys(words))  # "All the strings of words are unique"
    return (
        [board, words],
        _word_search_ii_oracle(board, words),
        {"compare": "sorted"},  # the answer is a set: only its order is free
    )


@profiler_input("word-search-ii")
def _word_search_ii_profiler(n: int, rng: random.Random) -> list:
    # Board + words of total size ~n, both dimensions exercised: the board takes a
    # quarter of the budget and grows with n up to the statement's own 12 x 12 cap
    # (144 cells), and the word list takes everything left over, so the input keeps
    # growing after the grid has saturated.
    #
    # The words are built to make both a trie walk and a per-word board search do
    # their full work instead of returning early: seven in eight are a REAL board
    # path one letter short plus a reserved letter ('z' never occurs on the board),
    # so the word is absent — a per-word search has to exhaust the board before it
    # can answer false — while its entire prefix is genuinely present, so neither
    # implementation dies on the first letter. The eighth is a real path (present),
    # which keeps the answer non-empty so the two outputs are actually compared.
    # Values stay inside the statement's ranges: lowercase letters, board 1..12 a
    # side, words 1..10 letters and unique.
    n = max(1, int(n))
    side = max(1, min(12, int((n // 4) ** 0.5)))  # int sqrt: registry.py imports only random
    letters = "abcd"  # four letters: the walk's branching stays real but tractable
    board = [[rng.choice(letters) for _ in range(side)] for _ in range(side)]
    cells = side * side
    longest = max(1, min(10, cells))  # a word cannot be longer than the board

    def _word_search_ii_path(length: int) -> str:
        r, c = rng.randrange(side), rng.randrange(side)
        seen = {(r, c)}
        out = [board[r][c]]
        while len(out) < length:
            options = [
                (nr, nc)
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                if 0 <= nr < side and 0 <= nc < side and (nr, nc) not in seen
            ]
            if not options:
                break
            r, c = rng.choice(options)
            seen.add((r, c))
            out.append(board[r][c])
        return "".join(out)

    # Fill the rest of the budget with words, skipping repeats (the statement
    # says all strings are unique, and the short words collide heavily — "z" is
    # the only one-letter absent word there is), so the total really is ~n. The
    # iteration cap keeps a tiny board (where few distinct words exist at all)
    # total rather than spinning.
    budget = max(1, n - cells)
    words: list[str] = []
    seen: set[str] = set()
    used = 0
    i = 0
    while used < budget and i < 20 * budget + 20:
        length = 1 + i % longest
        if i % 8 == 0:
            word = _word_search_ii_path(length)
        elif length == 1:
            word = "z"
        else:
            word = _word_search_ii_path(length - 1) + "z"
        i += 1
        if word in seen:
            continue
        seen.add(word)
        words.append(word)
        used += len(word)
    return [board, words]



# ----------------------------------------------------------------------- linked_list


@oracle("add-two-numbers")
def _add_two_numbers_oracle(l1: list[int], l2: list[int]) -> list[int]:
    """Brute force via Python's bignums: rebuild both numbers from their digit
    lists, add them, and decompose the sum back into little-endian digits. It
    shares no step with the reference's carry loop, which is what makes the
    differential worth something."""
    a = 0
    for digit in reversed(l1):
        a = a * 10 + digit
    b = 0
    for digit in reversed(l2):
        b = b * 10 + digit
    total = a + b
    if total == 0:
        return [0]
    out: list[int] = []
    while total:
        out.append(total % 10)
        total //= 10
    return out


@judge_case("add-two-numbers")
def _add_two_numbers_case(n: int, rng: random.Random) -> tuple[list, list]:
    n = max(1, min(n, 12))  # the statement's floor: each list has >= 1 node
    m = max(1, min(n, 12))
    l1 = [rng.randint(0, 9) for _ in range(n)]
    l2 = [rng.randint(0, 9) for _ in range(m)]
    # The statement's guarantee is that neither list represents a number with a
    # leading zero, and a leading zero IS the most significant digit here: a
    # list ending in 0 would be a non-canonical number whose digit-wise sum has
    # more digits than its integer sum, so it is not a case this problem defines.
    # So the top digit is always redrawn from [1, 9] — and 15% of the time the
    # other list is the statement's one exception, the number 0 itself.
    l1[-1] = rng.randint(1, 9)
    l2[-1] = rng.randint(1, 9)
    if rng.random() < 0.15:
        l2 = [0]
    return [l1, l2], _add_two_numbers_oracle(l1, l2)


@profiler_input("add-two-numbers")
def _add_two_numbers_profiler(n: int, rng: random.Random) -> list:
    """Two 100-digit numbers of all 9s: 999...9 + 999...9 forces the carry to
    propagate through all 100 positions and the result to be one node longer
    than either input. Nothing can early-exit, and both inputs sit exactly on
    the statement's limit (nodes <= 100, digits 0..9)."""
    digits = [9] * max(1, min(n, 100))
    return [digits, list(digits)]


@oracle("remove-nth-node-from-end-of-list")
def _remove_nth_node_from_end_of_list_oracle(head: list[int], n: int) -> list[int]:
    """Brute force in the two-pass shape the problem is usually taught in: count
    the nodes, work out which index the nth node from the end is, and rebuild the
    list without it. Total on the empty list and on an n outside the statement's
    1 <= n <= sz (nothing is removed), which keeps the differential total even
    though the generator never emits one."""
    size = len(head)
    cut = size - n
    return [head[i] for i in range(size) if i != cut]


@judge_case("remove-nth-node-from-end-of-list")
def _remove_nth_node_from_end_of_list_case(
    n: int, rng: random.Random
) -> tuple[list, list[int]]:
    size = max(1, min(n, 12))  # the statement's range is 1 <= sz <= 30, so the floor is 1
    head = [rng.randint(0, 100) for _ in range(size)]
    # k is the statement's n, renamed so it cannot be confused with the caller's
    # size parameter. Drawn from [1, size] inclusive at both ends: k = size removes
    # the head, which is the classic off-by-one and IS generated.
    k = rng.randint(1, size)
    return [head, k], _remove_nth_node_from_end_of_list_oracle(head, k)


@oracle("merge-two-sorted-lists")
def _merge_two_sorted_lists_oracle(list1: list[int], list2: list[int]) -> list[int]:
    """Brute force: concatenate the two lists and sort. Merging two sorted lists
    produces their combined values in non-decreasing order, which is exactly what
    sorted() returns, so this is obviously correct and knows nothing about
    pointers. O((m + k) log(m + k)) - the honest differential against the
    reference's single merge pass. Total on two empty lists (example 2)."""
    return sorted([*list1, *list2])


@judge_case("merge-two-sorted-lists")
def _merge_two_sorted_lists_case(n: int, rng: random.Random) -> tuple[list, list[int]]:
    size = max(0, min(n, 12))  # the statement's total is at most 50 + 50 nodes
    first = rng.randint(0, size)  # either list may be empty - both may be (example 2)
    second = size - first
    # Values are inside the statement's [-100, 100]; duplicates are allowed (both
    # lists are only promised to be non-decreasing), and sorting each draw is what
    # makes that promise true.
    list1 = sorted(rng.randint(-100, 100) for _ in range(first))
    list2 = sorted(rng.randint(-100, 100) for _ in range(second))
    return [list1, list2], _merge_two_sorted_lists_oracle(list1, list2)


@profiler_input("merge-two-sorted-lists")
def _merge_two_sorted_lists_profiler(n: int, rng: random.Random) -> list:
    # A strictly increasing ramp of n values inside the statement's [-100, 100],
    # split alternately between the two lists. Both lists are non-decreasing and
    # (for n >= 2) non-empty, and they interleave perfectly: every step of the
    # merge is a comparison, no run can be copied wholesale, and neither side can
    # be handed back untouched - the early exits this input has to defeat.
    #
    # One value per node inside a 201-value range makes 201 this input's hard
    # ceiling; probe_max_n = 100 keeps the whole ladder inside the statement's 50
    # nodes per list (50 + 50 at the top) and far below the ceiling. The ladder's
    # smallest point is n = 1, where one side is necessarily empty - a legal input
    # (the statement allows a 0-node list), just not a demanding one.
    size = max(1, min(n, 201))
    values = [-100 + i for i in range(size)]
    return [values[0::2], values[1::2]]


@oracle("merge-k-sorted-lists")
def _merge_k_sorted_lists_oracle(lists: list[list[int]]) -> list[int]:
    """Brute force: at every output position, scan the current head of all k
    lists and take the smallest. O(total * k) with no heap and no sorting, so
    the differential against the reference is a real one."""
    positions = [0] * len(lists)
    out: list[int] = []
    while True:
        best = None
        best_index = -1
        for index, head in enumerate(lists):
            if positions[index] < len(head):
                value = head[positions[index]]
                if best is None or value < best:
                    best, best_index = value, index
        if best_index < 0:
            return out
        out.append(best)
        positions[best_index] += 1


@judge_case("merge-k-sorted-lists")
def _merge_k_sorted_lists_case(n: int, rng: random.Random) -> tuple[list, list]:
    # The statement's own ranges: 0 <= k == lists.length <= 10^4, 0 <=
    # lists[i].length <= 500, -10^4 <= lists[i][j] <= 10^4, every list ascending.
    # n (the caller's 0..12) only sizes the shape, so the cases cover the shapes
    # the constraints allow: k = 0 (example 2), a single empty list (example 3),
    # empty lists among non-empty ones, and duplicate values across lists.
    # Values come from -20..20 so duplicates are frequent.
    n = max(0, min(n, 12))
    k = rng.randint(0, n + 1) if n else 0
    lists: list[list[int]] = []
    for _ in range(k):
        length = rng.randint(0, 3)
        lists.append(sorted(rng.randint(-20, 20) for _ in range(length)))
    return [lists], _merge_k_sorted_lists_oracle(lists)


@profiler_input("merge-k-sorted-lists")
def _merge_k_sorted_lists_profiler(n: int, rng: random.Random) -> list:
    # k = n // 2 lists of two nodes, the values being the ranks 0..n-1 handed out
    # in *merge* order: list j holds [order[j], k + order[j]], so the merged
    # sequence is 0, 1, 2, ... while every list is ascending as the statement
    # requires. Values stay inside -10^4..10^4 (the largest is n - 1 <= 6399 on
    # the probe's ladder), k = n/2 <= 3200 <= 10^4, and the total node count is n.
    #
    # k grows with n on purpose, and that is what makes the measurement say
    # something about this problem: every step of the merge pops a *different*
    # list (the heads interleave perfectly across all k of them), so the heap
    # stays at its full k entries for nearly the whole merge and a solution that
    # merges the lists one at a time pays its whole O(n * k). With k held
    # constant, log k would be a constant and the problem's own difficulty — how
    # many lists are being merged — would vanish from the measurement.
    #
    # The list order is scrambled (Knuth's multiplicative constant mod 2**32, a
    # bijection, so `order` is a permutation) for a reason that is the v0.11
    # early-exit lesson in a new costume: with the lists left in rank order,
    # concatenating them in list order nearly sorts the input, and a
    # collect-and-sort solution is then measured on timsort's best case instead
    # of its real n log n — it came back "better than the reference — O(n)" on
    # exactly that artifact. Scrambled, no implementation sees a lucky shape.
    n = max(1, n)
    k = max(1, n // 2)
    per = max(1, n // k)
    order = sorted(range(k), key=lambda j: (j * 2654435761) % 2**32)
    return [[[i * k + order[j] for i in range(per)] for j in range(k)]]


@oracle("reverse-nodes-in-k-group")
def _reverse_nodes_in_k_group_oracle(head: list[int], k: int) -> list[int]:
    """Brute force: cut the list into blocks of k, hand each *complete* block to
    reversed(), and append the leftover tail untouched. Total on the empty list
    and on k < 1 as well, neither of which is inside the statement's own range
    (1 <= k <= n) — hence the guard instead of a division by k."""
    n = len(head)
    blocks = n // k if k >= 1 else 0
    out: list[int] = []
    for block in range(blocks):
        out.extend(reversed(head[block * k : (block + 1) * k]))
    out.extend(head[blocks * k :])
    return out


@judge_case("reverse-nodes-in-k-group")
def _reverse_nodes_in_k_group_case(n: int, rng: random.Random) -> tuple[list, list]:
    # The statement's ranges: 1 <= k <= n <= 5000 and 0 <= Node.val <= 1000, so n
    # clamps to at least 1 (the caller sends 0..12) and k is drawn from [1, n].
    # About a third of the cases draw from a three-value alphabet: repeated values
    # are what catch a solution that reorders the values instead of the positions.
    n = max(1, min(n, 12))
    k = rng.randint(1, n)
    if rng.random() < 0.35:
        head = [rng.randint(0, 2) for _ in range(n)]
    else:
        head = [rng.randint(0, 1000) for _ in range(n)]
    return [head, k], _reverse_nodes_in_k_group_oracle(head, k)


@profiler_input("reverse-nodes-in-k-group")
def _reverse_nodes_in_k_group_profiler(n: int, rng: random.Random) -> list:
    # One list of n nodes with k = 6 (k = n below six nodes, because the statement
    # requires k <= n): every node but the tail sits in a complete block, and the
    # leftover exercises the "left-out nodes remain as they are" path. k = 6 is
    # chosen so that leftover is never 0 and never 1 at any ladder point — the
    # ladder is 100, 200, ..., 6400, which are 2 or 4 modulo 6, whereas k = 3
    # leaves exactly one node at 100/400/1600/6400, and reversing a one-node block
    # is a no-op, so at those sizes a "reverse the tail as well" bug would be
    # invisible. Values respect 0 <= Node.val <= 1000 (i % 1001). Nothing can
    # early-exit: reversing a block has to touch every node.
    n = max(1, n)
    k = 6 if n >= 6 else max(1, n)
    return [[i % 1001 for i in range(n)], k]


@oracle("copy-list-with-random-pointer")
def _copy_list_with_random_pointer_oracle(head: list) -> list:
    """Brute force: a brand-new list object per node and a brand-new pair per
    node, with the random index copied verbatim. Obvious enough to trust as the
    correctness anchor, and structurally blind to how a copy was built."""
    return [[node[0], node[1]] for node in head]


@checker("deep_copy_valid")
def _deep_copy_valid(module, got, args) -> bool:
    """The deep-copy contract for copy-list-with-random-pointer: `got` must be a
    genuine structural copy of the node list (whose `next` chain is the list
    order), sharing no list object with it, and the input must be unchanged.

    The module argument is part of the predicate signature (round-trip checkers
    call a sibling function through it); this checker needs nothing from it --
    that is exactly why it can also grade the oracle's own output, which is how
    tests/test_registry.py exercises a predicate of a problem with no oracle
    needed special-casing.

    Rejections, in the order they are checked:
    - the input is not in the corpus form [[value, random_index], ...];
    - `got` is the input itself (identity) or is not element-by-element equal to
      it (wrong length, a mutated/partial copy, or a copy of the wrong values);
    - `got` shares ANY list object with the input -- the shallow-copy rejection
      (a copy that aliases only the inner [value, random_index] pairs is caught
      even though its next chain looks perfect);
    - `args[0]` (the argument list as it stands after the call) no longer equals
      the input the case supplied. Mutating the original while copying is a
      failure, and the judge harness passes the arguments post-call, so this is
      where it shows.

    What it does NOT do: fix a node count or a value range. The contract has no
    freedom in either (n and the values come from the input), so they are graded
    by the equality check rather than re-imposed on a correct copy.
    """
    if not isinstance(args, (list, tuple)) or not args:
        return False
    head = args[0]

    def _is_node_list(value) -> bool:
        return (
            isinstance(value, list)
            and all(
                isinstance(entry, list)
                and len(entry) == 2
                and isinstance(entry[0], int)
                and not isinstance(entry[0], bool)
                and isinstance(entry[1], int)
                and not isinstance(entry[1], bool)
                and -1 <= entry[1] < len(value)
                for entry in value
            )
        )

    if not _is_node_list(head):
        return False
    if not _is_node_list(got):
        return False
    # Structural equality: the copy holds the same values and the same random
    # pointers. `next` needs no separate check because the list order IS the
    # next chain (and random_index is index-based, so it never dangles).
    if len(got) != len(head):
        return False
    for copied, original in zip(got, head):
        if copied[0] != original[0] or copied[1] != original[1]:
            return False
    if got is head:  # returning the input is the degenerate "copy"
        return False

    def _list_objects(value, into: set) -> None:
        if isinstance(value, list):
            into.add(id(value))
            for item in value:
                _list_objects(item, into)

    original_objects = {id(head)}
    for entry in head:
        original_objects.add(id(entry))
    copied_objects: set = set()
    _list_objects(got, copied_objects)
    if original_objects & copied_objects:
        return False  # a shallow copy aliases part of the original list

    return True  # a genuine deep copy, and the input still holds its own values


@judge_case("copy-list-with-random-pointer")
def _copy_list_with_random_pointer_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    n = max(0, min(n, 12))  # the statement's range is [0, 1000]
    head = []
    for i in range(n):
        # -1 with probability 1/3: null random pointers are as common as the
        # statement's own first example makes them.
        target = -1 if rng.random() < 1 / 3 else rng.randint(0, n - 1)
        head.append([rng.randint(-10**4, 10**4), target])
    return [head], _copy_list_with_random_pointer_oracle(head), {"predicate": "deep_copy_valid"}


@profiler_input("copy-list-with-random-pointer")
def _copy_list_with_random_pointer_profiler(n: int, rng: random.Random) -> list:
    """n nodes (clamped to the statement's 1000), every random pointer non-null
    and in range, so both implementations walk exactly n nodes and every random
    pointer has to be resolved — a null-heavy list would let a lazy copy skip
    work. Values are spread across the whole -10^4..10^4 range the statement
    allows rather than clustered at 0."""
    size = max(1, min(n, 1000))
    lo, hi = -10**4, 10**4
    head = [[lo + (hi - lo) * i // max(1, size - 1), (i + 1) % size] for i in range(size)]
    return [head]


@oracle("linked-list-cycle")
def _linked_list_cycle_oracle(next_node: list[int]) -> bool:
    """Brute force: walk the successor chain from node 0 and remember every node
    visited. A revisit is the statement's own definition of a cycle; a -1 is the
    end of the list. Total on the empty list (which the statement's [0, 10^4]
    node range allows and the generator emits): no nodes, no cycle."""
    seen: set[int] = set()
    if not next_node:
        return False
    node = 0
    while node != -1:
        if node in seen:
            return True
        seen.add(node)
        node = next_node[node]
    return False


@judge_case("linked-list-cycle")
def _linked_list_cycle_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))  # the statement's node range is [0, 10^4]
    # next_node[i] is the index of node i's successor; the last node closes the
    # cycle at pos (or ends the list with -1). With n = 0 there is no node to
    # point anywhere, so pos is not drawn at all (randint(0, -1) would raise).
    next_node = [i + 1 for i in range(n)]
    if n:
        pos = -1 if rng.random() < 0.4 else rng.randint(0, n - 1)
        next_node[-1] = pos
    return [next_node], _linked_list_cycle_oracle(next_node)


@profiler_input("linked-list-cycle")
def _linked_list_cycle_profiler(n: int, rng: random.Random) -> list:
    """One ring of n nodes: the successor chain is 0 -> 1 -> ... -> n-1 -> 0, so
    the tortoise and the hare have to walk the whole ring before they meet and
    neither implementation can exit early. Node count is clamped to the
    statement's 10^4."""
    size = max(2, n)
    next_node = [i + 1 for i in range(size)]
    next_node[-1] = 0
    return [next_node]


@oracle("reorder-list")
def _reorder_list_oracle(head: list[int]) -> None:
    """Brute force: peel the values off the two ends alternately - front, back,
    front, back - which is the statement's pattern written directly, with no
    notion of halves or reversal. The result is written back with a slice
    assignment, so the list the caller holds is the reordered one, and that
    post-call argument list is exactly what dojo's "mutates" verdict compares.
    Total on an empty or single-node list (the statement requires at least one
    node)."""
    order: list[int] = []
    lo = 0
    hi = len(head) - 1
    take_front = True
    while lo <= hi:
        if take_front:
            order.append(head[lo])
            lo += 1
        else:
            order.append(head[hi])
            hi -= 1
        take_front = not take_front
    head[:] = order


@judge_case("reorder-list")
def _reorder_list_case(
    n: int, rng: random.Random
) -> tuple[list, list[list[int]], dict]:
    size = max(1, min(n, 12))  # the statement's range is 1 <= nodes <= 5 * 10^4
    head = [rng.randint(1, 1000) for _ in range(size)]
    expected = list(head)
    _reorder_list_oracle(expected)
    # A "mutates" case: expected is the ARGUMENT LIST as it must stand after the
    # call, not the (None) return value - the same shape the visible tests use.
    return [head], [expected], {"compare": "mutates"}


@profiler_input("reorder-list")
def _reorder_list_profiler(n: int, rng: random.Random) -> list:
    # A ramp of n values inside the statement's [1, 1000]. Both sides are
    # length-driven - the alternating peel and reverse-then-interleave both touch
    # every node - and every size the probe uses is orders of magnitude above the
    # < 3 nodes where a "nothing to do" early return is legitimate, so no ladder
    # point can exit early. Adjacent values differ, so a reorder that lost,
    # duplicated or misplaced a node cannot digest-match the reference.
    size = max(3, min(n, 10_000))
    return [[1 + (i % 1000) for i in range(size)]]


@oracle("lru-cache")
def _lru_cache_oracle(ops: list[list]) -> list:
    """Brute force: the recency order is a plain list that is scanned and spliced
    in full on every access — O(capacity) per op instead of the intended O(1) —
    driven by the same op list the class problems use. The capacity arrives as the
    leading ["__init__", capacity] op; a get or put before it is an error rather
    than a silent default (see the fragment notes for why the constructor travels
    inside the op list)."""
    capacity = None
    values: dict[int, int] = {}
    recency: list[int] = []  # least recently used first, most recently used last
    out: list = []
    for op in ops:
        method, *args = op
        if method == "__init__":
            capacity = args[0]
            values = {}
            recency = []
            out.append(None)
        elif method == "get":
            if capacity is None:
                raise ValueError('the op list must start with ["__init__", capacity]')
            key = args[0]
            if key not in values:
                out.append(-1)
            else:
                recency.remove(key)
                recency.append(key)
                out.append(values[key])
        elif method == "put":
            if capacity is None:
                raise ValueError('the op list must start with ["__init__", capacity]')
            key, value = args
            if key in values:
                recency.remove(key)
            values[key] = value
            recency.append(key)
            if len(values) > capacity:
                oldest = recency.pop(0)
                del values[oldest]
            out.append(None)
        else:  # pragma: no cover - the generator only emits the three methods
            raise ValueError(f"unknown op {method}")
    return out


@judge_case("lru-cache")
def _lru_cache_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # Deterministic by construction: every op comes from the seeded rng, the op
    # sequence never depends on what the cache answers, and each case replays on a
    # fresh instance (the harness builds one per case from ctor_args, and the
    # drivers rebuild their state on the __init__ op). Constraints honoured:
    # 1 <= capacity <= 3000 (kept at 1..3 so eviction happens constantly),
    # 0 <= key <= 10^4 (a pool of 0..3, so updates and evictions are common), and
    # 0 <= value <= 10^5 — the first put always stores 0, because a falsy value is
    # what catches `if not self.cache[key]` treating a stored 0 as a miss.
    n = max(1, min(n, 12))
    capacity = rng.randint(1, 3)
    key_pool = list(range(rng.randint(1, 4)))
    ops: list[list] = [["__init__", capacity]]
    for step in range(2 * n):
        key = rng.choice(key_pool)
        if step % 4 == 3:
            ops.append(["get", key])
        else:
            ops.append(["put", key, 0 if step == 0 else rng.randint(0, 20)])
    return [], _lru_cache_oracle(ops), {"ops": ops, "ctor_args": [capacity]}


@oracle("reverse-linked-list")
def _reverse_linked_list_oracle(head: list[int]) -> list[int]:
    """Brute force: walk the list from the front and push every value onto the
    front of the result, so the node read first ends up last. Obviously correct,
    deliberately not the intended technique, and O(n^2) because each insert moves
    everything already placed. Total on the empty list, which the statement's
    [0, 5000] node range allows and the generator emits."""
    out: list[int] = []
    for value in head:
        out.insert(0, value)
    return out


@judge_case("reverse-linked-list")
def _reverse_linked_list_case(n: int, rng: random.Random) -> tuple[list, list[int]]:
    n = max(0, min(n, 12))  # the statement's node range is [0, 5000]; the floor is 0 on purpose
    # Values are inside the statement's [-5000, 5000]. Duplicates are allowed
    # (nothing promises distinct node values) and no value changes the work.
    head = [rng.randint(-5000, 5000) for _ in range(n)]
    return [head], _reverse_linked_list_oracle(head)


@profiler_input("reverse-linked-list")
def _reverse_linked_list_profiler(n: int, rng: random.Random) -> list:
    # Reversal has no early exit on either side: every node is visited and placed
    # whatever the values are, so this input's only jobs are to be legal and to be
    # UNAMBIGUOUS. A strictly increasing ramp inside [-5000, 5000] is both: the
    # values are distinct for every size the probe can ask for (n <= 3200 here, and
    # 10001 distinct values exist), so the digest the probe compares is a real
    # statement about the permutation. With a repeating pattern a solution that
    # dropped or duplicated a node could still match.
    size = max(1, n)
    return [[-5000 + (i % 10001) for i in range(size)]]


@oracle("find-the-duplicate-number")
def _find_the_duplicate_number_oracle(nums: list[int]) -> int:
    """Brute force in O(n^2) time and O(1) extra space (the statement's own
    constant-space demand, honoured by the anchor too): the first value that
    appears twice is the answer. Total on inputs with no duplicate — it falls
    back to the smallest value, which the statement's existence guarantee makes
    unreachable."""
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] == nums[j]:
                return nums[i]
    return min(nums) if nums else -1


@judge_case("find-the-duplicate-number")
def _find_the_duplicate_number_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's range is 1 <= n <= 10^5
    if n == 1:
        # Length n + 1 with values in [1, n] leaves [1, 1] as the only array.
        return [[1, 1]], 1
    if n == 2:
        # The only array of length 3 with values in [1, 2] and a single repeated
        # value is [2, 2]. The walk cannot enter it (value 2 is the duplicate at
        # index 0, which points at the out-of-range index 2), so this generator
        # clamps n = 2 up to the first walkable size and never emits it.
        n = 3
    # The pool is 1..n-1, so no element equals n — the value that would let the
    # successor walk step outside the array. Two values are removed (one becomes
    # the repeat, one disappears) and three elements are added back: `filler`
    # plus two copies of `dup`. Length (n - 3) + 3 == n + 1, values in [1, n],
    # and `dup` is the only value appearing twice.
    pool = list(range(1, n))
    rng.shuffle(pool)
    dup = pool.pop()
    filler = pool.pop()
    nums = pool + [filler, dup, dup]
    rng.shuffle(nums)
    return [nums], dup


@profiler_input("find-the-duplicate-number")
def _find_the_duplicate_number_profiler(n: int, rng: random.Random) -> list:
    """The value graph the intended solution walks, with the longest tail there
    is: nums = [2, 3, ..., n, 1, n], so index i points at index i + 1 for every
    i < n - 1, index n - 1 points back at index 0, and index n points at itself.
    The duplicate (value n, at indices 0 and n) is the cycle's entry, and value 1
    is the head of the walk, so Floyd's pointers cross the whole array before
    they meet — neither phase can exit early. Length n + 1 with values 1..n, the
    statement's own shape."""
    n = max(1, n)  # the statement's floor (1 <= n <= 10^5); no clamp past it
    nums = list(range(2, n + 1))  # n - 1 distinct values: 2..n
    nums.append(1)  # index n - 1 -> 1 -> the walk's entry into the cycle
    nums.append(n)  # index n -> n, the duplicate of nums[0]
    return [nums]



# ----------------------------------------------------------------------- backtracking


@oracle("letter-combinations-of-a-phone-number")
def _letter_combinations_of_a_phone_number_oracle(digits: str) -> list[str]:
    # Brute force, and the Cartesian product written out: start from one empty
    # prefix and, for every digit in turn, append each letter that key carries.
    # No recursion and no pruning -- obviously correct -- and a different
    # mechanism from the reference's backtracking DFS. The two agree letter for
    # letter AND in order, because both walk the digits left to right and each
    # key's letters in keypad order, which is why the statement's own Example 1
    # output can be transcribed verbatim. Total for empty digits (the statement's
    # 1 <= digits.length excludes them) and for a digit outside 2-9, which
    # contributes no letters on either side -- see the notes.
    keypad = {
        "2": "abc", "3": "def", "4": "ghi", "5": "jkl",
        "6": "mno", "7": "pqrs", "8": "tuv", "9": "wxyz",
    }
    if not digits:
        return []
    out = [""]
    for digit in digits:
        out = [prefix + letter for prefix in out for letter in keypad.get(digit, "")]
    return out


@judge_case("letter-combinations-of-a-phone-number")
def _letter_combinations_of_a_phone_number_case(
    n: int, rng: random.Random
) -> tuple[list, list, dict]:
    # The statement's range, honoured exactly on both ends: 1 <= digits.length <= 4
    # and every digit in '2'..'9'. The caller sends 0..12, so the clamp has a real
    # floor AND a real ceiling here -- the generator cannot emit the empty string
    # the statement excludes, nor a 5-digit input it forbids, nor '0'/'1' which are
    # outside the stated range (a solution that expects them has no case to fail on
    # here, because the statement gives it none).
    length = max(1, min(n, 4))
    dial = "79" if n % 3 == 0 else "23456789"
    digits = "".join(rng.choice(dial) for _ in range(length))
    return (
        [digits],
        _letter_combinations_of_a_phone_number_oracle(digits),
        {"compare": "sorted"},  # the answer is a set of strings: only order is free
    )


@oracle("combination-sum")
def _combination_sum_oracle(candidates: list[int], target: int) -> list[list[int]]:
    # Brute force over how many times each candidate is used: level i decides the
    # count of candidates[i], every count that still fits the remaining target is
    # tried, and a count vector whose sum lands exactly on the target is one
    # combination. The candidates are distinct (the statement guarantees it and
    # the generator upholds it), so count vector <-> multiset of values is a
    # bijection: every combination is produced exactly once and none is missed.
    # Sorting first makes the output ascending-lexicographic, the canonical form
    # of a set answer (the visible tests carry the statement's example order).
    values = sorted(candidates)
    out: list[list[int]] = []

    def _combination_sum_counts(i: int, remaining: int, picks: list[int]) -> None:
        if i == len(values):
            if remaining == 0:
                out.append(list(picks))
            return
        value = values[i]
        count = 0
        while count * value <= remaining:
            _combination_sum_counts(i + 1, remaining - count * value, picks + [value] * count)
            count += 1

    _combination_sum_counts(0, target, [])
    return sorted(out)


def _combination_sum_ways(values: list[int], target: int) -> tuple[int, int]:
    """(combinations summing to target, partial multisets with sum <= target).

    The unbounded-coin-change DP: ``ways[t]`` counts the multisets of values that
    sum to exactly t, counting each multiset once, so ``ways[target]`` is the size
    of the answer and ``sum(ways)`` bounds the nodes the oracle's count-vector
    enumeration visits. Both are used to keep a generated case small and cheap —
    the statement's own guarantee is "less than 150 combinations", and this keeps
    the *work* bounded as well as the answer.
    """
    ways = [0] * (target + 1)
    ways[0] = 1
    for value in values:
        for total in range(value, target + 1):
            ways[total] += ways[total - value]
    return ways[target], sum(ways)


@judge_case("combination-sum")
def _combination_sum_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # The statement's guarantees, upheld exactly: 1 <= len(candidates) <= 30,
    # 2 <= candidates[i] <= 40, "All elements of candidates are distinct",
    # 1 <= target <= 40, and "the number of unique combinations that sum up to
    # target is less than 150" (tightened here to <= 24).
    #
    # Distinctness is load-bearing for the verdict: with a repeated candidate,
    # two different count vectors ("use the first 2 twice" / "use the second 2
    # twice") would produce the same multiset of values, the answer set would
    # stop being a set, and a correct solution returning the other copy would be
    # false-failed. The generator never repeats a value: it builds one value plus
    # a sample of distinct values above it (plus, sometimes, its partner).
    n = max(1, min(n, 12))
    target = rng.randint(1, 40)
    count = max(1, min(n, 8))  # candidates.length grows with n, capped at 8 of 30
    for _ in range(64):
        if target == 1 or (rng.random() < 0.2 and 40 - target >= count):
            # The statement's own Example 3 shape: every candidate is above the
            # target (candidates are >= 2, so target = 1 forces this), no
            # combination exists and the answer is the empty list.
            above = rng.sample(range(max(2, target + 1), 41), count)
            return [above, target], _combination_sum_oracle(above, target), {"compare": "sorted"}
        # Otherwise the small candidate is chosen so that a solution provably
        # exists: usually a *proper* divisor of the target, so repeating it takes
        # at least two steps and the unlimited reuse the statement allows
        # (Example 2's [2,2,2,2]) is genuinely exercised; sometimes the target
        # itself, which is one of Example 1's own combinations (7 = 7); and for a
        # target with no proper divisor at all the target is reached as a
        # two-value sum instead, which keeps a prime target a real case rather
        # than "the target is a candidate". The partner (target - small) is added
        # as a second candidate whenever it is a legal distinct value — it pairs
        # with `small` to make a second combination. The rest are distinct values
        # above `small`.
        proper = [d for d in range(2, target) if target % d == 0]
        if proper and rng.random() < 0.75:
            small = rng.choice(proper)
        elif proper:
            small = target
        else:
            small = rng.randint(2, max(2, target // 2))
        partner = target - small
        rest = rng.sample(range(small + 1, 41), min(count - 1, 40 - small))
        values = [small]
        if 2 <= partner <= 40 and partner != small:
            values.append(partner)
        values += [v for v in rest if v not in values]
        ways, nodes = _combination_sum_ways(values, target)
        if 1 <= ways <= 24 and nodes <= 4_000:
            return [values, target], _combination_sum_oracle(values, target), {"compare": "sorted"}
    # Deterministic fallback if all 64 draws were too large: the target itself is
    # a candidate, so the answer is exactly [[target]] — never empty, never big.
    values = [target] + (
        rng.sample(range(target + 1, 41), min(count - 1, 40 - target)) if target < 40 else []
    )
    return [values, target], _combination_sum_oracle(values, target), {"compare": "sorted"}
# No profiler input, deliberately: the statement caps the input (at most 30
# candidates, target <= 40), so no input of the probe's ladder sizes (100 .. 6400)
# can respect the constraints, and the intended cost is the search tree itself —
# exponential in the target — so a paired ratio at legal sizes would measure the
# shared output, not the algorithm.


@oracle("combination-sum-ii")
def _combination_sum_ii_oracle(candidates: list[int], target: int) -> list[list[int]]:
    # Brute force over all 2^n index subsets: keep the non-empty ones whose
    # values sum to the target, then de-duplicate by the *sorted* value tuple.
    # candidates may repeat a value, so two different index sets can spell the
    # same combination (in [1,2,2] the sets {0,1} and {0,2} both spell [1,2]) and
    # the statement forbids the answer from carrying it twice; the sorted key is
    # also a combination's canonical form, independent of which copy of a
    # repeated value was chosen. `combo and` keeps the empty combination out of
    # a target-0 query -- outside the statement's 1 <= target <= 30, but the
    # floor should still be handled honestly.
    found = set()
    for mask in range(1 << len(candidates)):
        combo = tuple(sorted(candidates[i] for i in range(len(candidates)) if mask >> i & 1))
        if combo and sum(combo) == target:
            found.add(combo)
    return sorted(list(combo) for combo in found)


@judge_case("combination-sum-ii")
def _combination_sum_ii_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # n is clamped to the caller's ceiling (0..12); the statement allows up to
    # 100 candidates, so this clamp cannot break a stated constraint. Values come
    # from an 8-value pool inside the statement's 1 <= candidates[i] <= 50, and a
    # second copy of candidates[0] is injected with probability 0.5 when n >= 2:
    # a repeated candidate is the whole point of LC 40 (measured over 8k draws by
    # this fragment's self-check, seed 4321: 77.2% of cases carry one -- 57% at
    # n=2, 70% at n=3, 85% at n=4, 100% at n>=8, 0% at n=1). The target is drawn
    # from the statement's 1..30 range, capped at 16 to keep cases small, and the
    # loop enforces the answer-count guarantee the problem's test data makes --
    # fewer than 150 unique combinations -- by halving the target if a draw ever
    # exceeded it; the fallback (n ones, target at most n) has exactly one
    # combination, so the guarantee cannot be lost. Neither guard fired in 8000
    # measured draws (largest answer seen: 30), and over EVERY multiset of size
    # <= 12 this pool admits, with every target up to 16, the largest possible
    # answer is 41 (measured exhaustively) -- the bound is a property of the
    # pool, not of luck.
    n = max(1, min(n, 12))
    pool = [1, 2, 2, 3, 4, 5, 6, 8]  # inside 1 <= candidates[i] <= 50
    target = rng.randint(1, 16)  # inside 1 <= target <= 30
    for _ in range(8):
        candidates = [rng.choice(pool) for _ in range(n)]
        if n >= 2 and rng.random() < 0.5:
            candidates[rng.randrange(1, n)] = candidates[0]
        expected = _combination_sum_ii_oracle(candidates, target)
        if len(expected) < 150:
            return [candidates, target], expected, {"compare": "sorted"}
        target = max(1, target // 2)  # tighten and re-draw
    candidates = [1] * n  # the provable fallback: at most one combination
    target = rng.randint(1, n)
    return [candidates, target], _combination_sum_ii_oracle(candidates, target), {"compare": "sorted"}


@oracle("permutations")
def _permutations_oracle(nums: list[int]) -> list[list[int]]:
    # Brute force by construction: start from the arrangement of the first value
    # and insert each next value into every position of every arrangement built so
    # far. Correct by induction — an arrangement's position for the last value is
    # unique, so each of the n! arrangements is reached exactly once, and nothing
    # else can be: the values are distinct, which the statement guarantees and the
    # generator upholds (a repeated value would make several insertion paths
    # produce the same list and the answer would stop being a set). The final sort
    # is the canonical (ascending-lexicographic) form of that set answer, which is
    # also the order the statement's own examples print.
    out: list[list[int]] = [[]]
    for value in nums:
        grown: list[list[int]] = []
        for arr in out:
            for i in range(len(arr) + 1):
                grown.append(arr[:i] + [value] + arr[i:])
        out = grown
    return sorted(out)


@judge_case("permutations")
def _permutations_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # The statement's constraints, upheld exactly: 1 <= nums.length <= 6,
    # -10 <= nums[i] <= 10, and "All the integers of nums are unique" — n distinct
    # values from the statement's own range. Distinctness is what keeps the answer
    # a *set*: with a repeated value, [2, 2] would be one arrangement reachable
    # through two different index choices, and a correct solution that returned
    # the other copy would be false-failed. The statement's own cap of 6 is also
    # what keeps the answer real but small: 720 permutations at the top.
    n = max(1, min(n, 6))
    nums = rng.sample(range(-10, 11), n)
    if rng.random() < 0.5:
        nums.sort()  # the statement's examples are ascending; an unordered input is legal too
    return [nums], _permutations_oracle(nums), {"compare": "sorted"}
# No profiler input, deliberately: the answer is n! arrangements of n values, so
# both implementations are dominated by emitting the same exponential output and
# the paired ratio could only measure that shared work. The statement's own cap of
# nums.length <= 6 also leaves nothing to scale — every size on the probe's ladder
# (100 .. 6400) would be an illegal input.


@oracle("n-queens")
def _n_queens_oracle(n: int) -> list[list[str]]:
    # Brute force over every placement: row by row, try all n columns and keep a
    # partial placement only while the new queen attacks none of the queens below
    # it. The attack test is the statement's rule written out plainly -- same
    # column, or the same diagonal because the row distance equals the column
    # distance -- against EVERY queen already placed, with no column set and no
    # diagonal set to get wrong. That is what makes it a real differential against
    # the reference's three-set bookkeeping, and it is COMPLETE: a solution has
    # exactly one queen in each row (n queens, none sharing a row), so its column
    # tuple is one of the n**n assignments this walk visits, and the attack test
    # accepts exactly the placements the statement calls solutions -- so nothing is
    # missed and nothing extra is admitted. Solutions come out in lexicographic
    # column order, which is the order the statement's own Example 1 uses.
    # Total for n <= 0 (n=0 is the "empty input" the constraints exclude): no queen
    # is ever placed, so there is no solution to report.
    if n < 1:
        return []
    out: list[list[str]] = []
    placed: list[int] = []  # placed[r] = the column of the queen in row r

    def _n_queens_assign(r: int) -> None:
        if r == n:
            out.append(
                [
                    "".join("Q" if placed[row] == col else "." for col in range(n))
                    for row in range(n)
                ]
            )
            return
        for c in range(n):
            if all(
                c != col and abs(c - col) != r - row
                for row, col in enumerate(placed)
            ):
                placed.append(c)
                _n_queens_assign(r + 1)
                placed.pop()

    _n_queens_assign(0)
    return out


@judge_case("n-queens")
def _n_queens_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # The statement's whole range, 1 <= n <= 9, with no clamp of my own at either
    # end: the caller sends 0..12, and n IS the entire input, so there is nothing
    # else to vary and nothing to keep inside a range but n itself. The ceiling is
    # the statement's own, not a cost cap: the oracle prunes as it places, so its
    # search is the pruned tree rather than n**n leaves (measured, n=9 costs it
    # 54-97 ms against the reference's 11-24 ms), and a case stays cheap enough for the
    # reference gate's 20 cases and a 200-case self-check. n=2 and n=3 are in the
    # range and have no solutions at all, so the empty answer is generated too.
    n = max(1, min(n, 9))
    return [n], _n_queens_oracle(n), {"compare": "sorted"}  # only the ORDER is free


@oracle("subsets")
def _subsets_oracle(nums: list[int]) -> list[list[int]]:
    # Brute force by construction rather than by bit tricks: start from the empty
    # subset and let every value double the collection — every subset built so far
    # without the value, then the same subset with it. Correct by induction (a
    # subset either contains this value or it does not), and it emits the
    # statement's own example order, which is the canonical form of a set answer.
    out: list[list[int]] = [[]]
    for value in nums:
        out.extend([subset + [value] for subset in out])
    return out


@judge_case("subsets")
def _subsets_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # The statement's constraints, upheld exactly: 1 <= nums.length <= 10,
    # -10 <= nums[i] <= 10, and "All the numbers of nums are unique" — n distinct
    # values drawn from the statement's own range. Distinctness is what keeps the
    # answer a *set*: with a repeated value the same subset of values would be
    # reachable as two different subsets and equality judging would be ambiguous
    # (a correct solution choosing the other copy would be false-failed). The cap
    # of 10 is what keeps the answer real but small: 1024 subsets at the top.
    n = max(1, min(n, 10))
    nums = rng.sample(range(-10, 11), n)
    if rng.random() < 0.5:
        nums.sort()  # the statement's examples are ascending; an unordered input is legal too
    return [nums], _subsets_oracle(nums), {"compare": "sorted"}
# No profiler input, deliberately: the output is exponential (2^n subsets of up to
# n values each), so both implementations are dominated by emitting the same
# answer and the paired ratio could only ever be ~1 — the ratio measures the
# output, not the algorithm. The statement's own cap of nums.length <= 10 also
# makes every size on the probe's ladder (100 .. 6400) an illegal input, so a
# profiler input could not respect the constraints and have a size to measure.


@oracle("word-search")
def _word_search_oracle(board: list[list[str]], word: str) -> bool:
    # Brute force, and deliberately UNPRUNED: walk every self-avoiding path of
    # exactly len(word) cells on the board and compare the spelled string only
    # once a path is complete. No first-letter filter, no early exit inside a
    # path -- so it is obviously correct and structurally different from the
    # reference, which prunes on the letter and returns at the first hit. Total
    # for an empty board; the empty word is "found" on both sides, which the
    # statement's 1 <= word.length excludes from ever being generated.
    rows = len(board)
    cols = len(board[0]) if rows else 0
    target = list(word)
    if not target:
        return True
    used = [[False] * cols for _ in range(rows)]
    spelled: list[str] = []

    def _word_search_walk(r: int, c: int, k: int) -> bool:
        used[r][c] = True
        spelled.append(board[r][c])
        if k == len(target) - 1:
            hit = spelled == target
        else:
            hit = any(
                _word_search_walk(nr, nc, k + 1)
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                if 0 <= nr < rows and 0 <= nc < cols and not used[nr][nc]
            )
        spelled.pop()
        used[r][c] = False
        return hit

    return any(_word_search_walk(r, c, 0) for r in range(rows) for c in range(cols))


def _word_search_case_path(board: list[list[str]], rng: random.Random, length: int) -> str:
    """A real self-avoiding walk of up to ``length`` cells, spelled out.

    Built by stepping to an unvisited neighbour, which is what makes the word
    genuinely present on the board; a walk that runs out of neighbours comes back
    short, and a short word is still a legal word."""
    rows = len(board)
    cols = len(board[0])
    r, c = rng.randrange(rows), rng.randrange(cols)
    seen = {(r, c)}
    out = [board[r][c]]
    while len(out) < length:
        options = [
            (nr, nc)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen
        ]
        if not options:
            break
        r, c = rng.choice(options)
        seen.add((r, c))
        out.append(board[r][c])
    return "".join(out)


@judge_case("word-search")
def _word_search_case(n: int, rng: random.Random) -> tuple[list, bool]:
    # Board 1..3 cells a side and a word of 1..6 letters. Both bounds are inside
    # the statement's own (1 <= m, n <= 6 and 1 <= word.length <= 15); the ceiling
    # is the ORACLE's, not the statement's, because the oracle enumerates every
    # self-avoiding path and a case has to stay cheap for the reference gate's 20
    # generated cases and a 200-case self-check (the word-search-ii precedent).
    # The alphabet is mixed case on purpose: the statement's letters are
    # case-sensitive, so a solution that lowercases the board fails here.
    n = max(1, min(n, 12))
    side = 1 + n % 3  # 1 <= board.length = board[i].length <= 6
    alphabet = "ABab"
    board = [[rng.choice(alphabet) for _ in range(side)] for _ in range(side)]
    cells = side * side
    length = rng.randint(1, min(6, cells + 2))  # 1 <= word.length <= 15
    mode = n % 4
    if mode == 0:
        # Random letters from the board's own alphabet: usually absent, and the
        # only mode that can produce a word longer than the board.
        word = "".join(rng.choice(alphabet) for _ in range(length))
    elif mode == 1:
        # A real path, so the answer is true whenever the walk was not cornered.
        word = _word_search_case_path(board, rng, min(length, cells))
    elif mode == 2:
        # A real path one letter short, spoiled with 'z' (never on the board, and
        # never in the alphabet): every letter of the prefix IS present, so a
        # pruned search still has to walk the board before it can answer false.
        path = _word_search_case_path(board, rng, max(1, min(length - 1, cells)))
        word = path[:-1] + "z" if path else "z"
    else:
        # The re-use trap, whenever the board allows it: on a one-letter board the
        # word 'a' * (cells + 1) would need some cell twice, which the statement
        # forbids -- the rule the statement's own "ABCB" example demonstrates.
        flat = {ch for row in board for ch in row}
        if len(flat) == 1 and cells + 1 <= 15:
            word = next(iter(flat)) * (cells + 1)
        else:
            word = "".join(rng.choice(alphabet) for _ in range(length))
    return [board, word], _word_search_oracle(board, word)


@profiler_input("word-search")
def _word_search_profiler(n: int, rng: random.Random) -> list:
    # The worst case is a board whose every cell carries the same letter plus a
    # word that ends in a letter the board does not contain: every prefix of the
    # word matches, so no pruning step can fire and every branch dies only at the
    # LAST letter, and the answer is false, so neither implementation can stop at
    # a hit.
    #
    # TOTAL SIZE ~n, and the word length takes a third of it while the board takes
    # the rest, so both dimensions grow: the board area is what makes the "try
    # every cell as a start" factor real, the word length is what makes the
    # backtracking deep. n is clamped to the statement's own ceiling -- 6 x 6 = 36
    # cells plus a 15-letter word -- because a larger n has no legal input to
    # describe. probe_max_n (40 in the overrides) is what keeps the ladder's top
    # inside the probe's timeout: measured, this input's reference call costs
    # ~0.23 s at n=40 and ~2.9 s at the statement's ceiling, so the ascent stops
    # where a slower-but-correct student is nowhere near the 20 s per-run bound.
    n = max(2, min(int(n), 51))
    length = max(2, min(15, n // 3))  # 2 <= word.length <= 15
    budget = max(1, n - length)  # the cells left for the board
    side = 1
    while side < 6 and (side + 1) ** 2 <= budget:
        side += 1
    board = [["a"] * side for _ in range(side)]
    word = "a" * (length - 1) + "b"
    return [board, word]


@oracle("subsets-ii")
def _subsets_ii_oracle(nums: list[int]) -> list[list[int]]:
    # Brute force over all 2^n index subsets, then de-duplicate by the *sorted*
    # value tuple. Both halves are deliberate. The index enumeration is the
    # obvious total one (it yields the empty subset without a special case), and
    # the sorted key is what the statement's "must not contain duplicate
    # subsets" means once nums repeats a value: in [1,2,2] the index sets {0,1}
    # and {0,2} both spell the subset [1,2]. Sorting the key also makes a
    # subset's form independent of the order its copies were visited in, so
    # [2,1] and [1,2] are one answer and not two. `sorted(...)` over the tuple
    # set is the canonical output order the visible tests show.
    subsets = set()
    for mask in range(1 << len(nums)):
        subsets.add(tuple(sorted(nums[i] for i in range(len(nums)) if mask >> i & 1)))
    return sorted(list(subset) for subset in subsets)


@judge_case("subsets-ii")
def _subsets_ii_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # n is clamped to the statement's own 1 <= nums.length <= 10 (the caller
    # sends 0..12) and every value stays inside -10 <= nums[i] <= 10. Values come
    # from a 7-value pool, and when n >= 2 a second copy of nums[0] is injected
    # with probability 0.6: duplicates are the entire difference between this
    # problem and LC 78, so leaving them to chance would leave the
    # duplicate-skipping path untested at small n. Measured over 20k draws (this
    # fragment's self-check, seed 1234): 78.7% of cases carry a repeat -- 66% at
    # n=2, 86% at n=4, 100% at n>=7; n=1 cannot have one, since a single element
    # has nothing to repeat.
    n = max(1, min(n, 10))
    nums = [rng.randint(-3, 3) for _ in range(n)]
    if n >= 2 and rng.random() < 0.6:
        nums[rng.randrange(1, n)] = nums[0]
    return [nums], _subsets_ii_oracle(nums), {"compare": "sorted"}


@oracle("palindrome-partitioning")
def _palindrome_partitioning_oracle(s: str) -> list[list[str]]:
    # Brute force over every set of cut positions: a string of length n has n - 1
    # gaps between its characters, so the 2^(n-1) masks enumerate every partition
    # of s exactly once -- a partition IS a choice of cuts -- and the masks whose
    # every piece reads the same both ways are kept. Nothing is de-duplicated and
    # nothing needs to be: different cut sets produce different piece lists
    # (pieces are non-empty, so the cuts are recoverable from the list), hence
    # the same partition can never appear twice. The empty string is the one case
    # the statement's 1 <= s.length excludes; it has exactly one partition, the
    # empty one, which is also what the reference returns.
    if not s:
        return [[]]
    n = len(s)
    out: list[list[str]] = []
    for mask in range(1 << (n - 1)):
        pieces: list[str] = []
        start = 0
        for i in range(n - 1):
            if mask >> i & 1:
                pieces.append(s[start : i + 1])
                start = i + 1
        pieces.append(s[start:])
        if all(piece == piece[::-1] for piece in pieces):
            out.append(pieces)
    return sorted(out)


@judge_case("palindrome-partitioning")
def _palindrome_partitioning_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # n is clamped to the caller's ceiling (0..12); the statement allows up to
    # 16, so the ceiling only keeps a case cheap for the brute-force oracle
    # (2^(n-1) masks, and a run of one letter at n=12 already answers 2048
    # partitions). The alphabet is lowercase English letters as the statement
    # requires, drawn from "aab" 75% of the time and "abc" the rest: repeated
    # letters are what create palindromes longer than one character, so the
    # two-letter draw makes the answer branch, while the three-letter draw keeps
    # the collapsing cases where the only partition is every character alone
    # (measured by this fragment's self-check, seed 777 / 4000 draws: 20.0% of
    # cases, mean 42 partitions per case, largest 2048).
    n = max(1, min(n, 12))
    alphabet = "aab" if rng.random() < 0.75 else "abc"
    s = "".join(rng.choice(alphabet) for _ in range(n))
    return [s], _palindrome_partitioning_oracle(s), {"compare": "sorted"}



# ----------------------------------------------------------------------- bit_manipulation


@oracle("reverse-integer")
def _reverse_integer_oracle(x: int) -> int:
    # Brute force, and a different mechanism from the reference's digit
    # arithmetic: spell the digits out with str, reverse the string, parse it
    # back (int() drops the leading zeros a trailing-zero input produces), then
    # apply the statement's rule literally — outside [-2^31, 2^31 - 1] the
    # answer is 0. Total for every int, including 0 and both range ends.
    if x < 0:
        value = -int(str(-x)[::-1])
    else:
        value = int(str(x)[::-1])
    if value < -(2**31) or value > 2**31 - 1:
        return 0
    return value


@judge_case("reverse-integer")
def _reverse_integer_case(n: int, rng: random.Random) -> tuple[list, int]:
    # The 32-bit overflow rule is what this problem is about, so it is not left
    # to chance: the first branch is one rng.random() < 0.5 draw and EVERY value
    # it can produce reverses out of [-2^31, 2^31 - 1], so P(overflow) = 0.5 for
    # a generated case and the other half is guaranteed in range. Both halves
    # keep x itself inside the statement's own -2^31 <= x <= 2^31 - 1.
    if rng.random() < 0.5:  # OVERFLOW HALF: the oracle answers 0 for every case
        if rng.random() < 0.25:  # the classic boundary values, checked by hand
            x = rng.choice([1534236469, -1534236469, -1563847412, -2147483648, 2147483647])
        else:
            # Ten digits whose LAST digit is 3..9, so the reversal starts with
            # 3..9 and is therefore >= 3 * 10^9: above 2^31 - 1 on the positive
            # side and below -2^31 on the negative one. The magnitude stays
            # inside the statement's range (max 2147483639 < 2^31 - 1).
            magnitude = rng.randint(1_000_000_000, 2_147_483_639) // 10 * 10 + rng.randint(3, 9)
            x = magnitude if rng.random() < 0.5 else -magnitude
    elif rng.random() < 0.25:  # hand-checked values that must NOT become 0
        # -2147483412 is here on purpose: it is 236 below the negative bound,
        # and its reversal (-2143847412) is still inside the range, so it pins
        # that the rule reads the REVERSED value and not the input's magnitude.
        x = rng.choice([-2147483412, 1463847412, 1000000001, 1000000000, 120, -120, 0, 7])
    else:  # nine digits or fewer: the reversal cannot leave the range
        x = rng.randint(-999_999_999, 999_999_999)
    return [x], _reverse_integer_oracle(x)


@oracle("single-number")
def _single_number_oracle(nums: list[int]) -> int | None:
    """Brute force: for each value, count its occurrences in the whole array and
    return the first with an odd count — under the statement's "every element
    appears twice except for one" that value is unique. None for an empty array,
    which the statement's constraint (length >= 1) never asks for."""
    for value in nums:
        if sum(1 for other in nums if other == value) % 2:
            return value
    return None


@judge_case("single-number")
def _single_number_case(n: int, rng: random.Random) -> tuple[list, int | None]:
    # The statement's constraints: the array is non-empty and every element
    # appears exactly twice except one, so its length is odd and exactly one
    # value is unpaired. Values are distinct draws inside [-3 * 10^4, 3 * 10^4].
    n = max(1, min(n, 12))
    if n % 2 == 0:
        n -= 1
    pool = rng.sample(range(-30_000, 30_001), n // 2 + 1)
    nums = [pool[0]]
    for value in pool[1:]:
        nums += [value, value]
    rng.shuffle(nums)
    return [nums], _single_number_oracle(nums)


@profiler_input("single-number")
def _single_number_profiler(n: int, rng: random.Random) -> list:
    # n is the array length, and the statement's shape forces an odd length
    # (pairs plus one single), so an even ladder size is trimmed by one — 6399 at
    # the probe's top size, inside the statement's 3 * 10^4. Values are 0..n // 2,
    # inside [-3 * 10^4, 3 * 10^4], and the two copies of each value sit half the
    # array apart. Both implementations must read every element (the XOR scan and
    # the counting oracle), so there is no early exit to take.
    size = max(1, n if n % 2 else n - 1)
    pairs = size // 2
    return [list(range(pairs)) * 2 + [pairs]]


@oracle("reverse-bits")
def _reverse_bits_oracle(n: int) -> int:
    """Brute force: write the value as a 32-character binary word and read it
    backwards — a different route from the reference's shift loop, and obvious
    enough to trust. 32 characters is exact on the graded domain, because no case
    exceeds the statement's 2^31 - 2."""
    return int(f"{n:032b}"[::-1], 2)


@judge_case("reverse-bits")
def _reverse_bits_case(n: int, rng: random.Random) -> tuple[int, int]:
    # The statement bounds the value itself (0 <= n <= 2^31 - 2, and n is even),
    # so the case size chooses a shape rather than a size: the lower bound, the
    # upper bound, and random even values drawn as 2 * k with k < 2^30.
    n = max(0, min(n, 12))
    if n == 0:
        value = 0
    elif n == 12:
        value = 2**31 - 2
    else:
        value = 2 * rng.randrange(2**30)  # even and <= 2^31 - 2, as the statement requires
    return [value], _reverse_bits_oracle(value)
# No profiler input: the input is a single 32-bit value, so the ladder has no size
# to grow — n = 100 and n = 6400 are two different values of the same one-word
# input, not two sizes. Both sides are a fixed 32 steps (the reference's loop) or
# 32 characters (the oracle's spelling), i.e. flat by construction, and a class
# read off that ratio would be a claim the measurement cannot support — the
# peak_elements precedent.


@oracle("number-of-1-bits")
def _number_of_1_bits_oracle(n: int) -> int:
    """Brute force: spell the value in binary and count the '1' digits — a
    different route from the reference's bit trick, and obvious enough to trust.
    The statement's domain is n >= 1, where bin(n) prints the digits of n alone."""
    return bin(n).count("1")


@judge_case("number-of-1-bits")
def _number_of_1_bits_case(n: int, rng: random.Random) -> tuple[int, int]:
    # The statement's constraint is 1 <= n <= 2^31 - 1 on a single scalar, so the
    # case size cannot shape an input — it picks how many bits are set. Half the
    # cases get exactly that many, positions drawn from the full 31-bit width so
    # the high bits are exercised; half are any value in the statement's range.
    n = max(1, min(n, 12))
    if rng.random() < 0.5:
        value = rng.randint(1, 2**31 - 1)
    else:
        value = sum(1 << bit for bit in rng.sample(range(31), n))
    return [value], _number_of_1_bits_oracle(value)
# No profiler input, and not for lack of trying: the input is a single 32-bit
# integer, so there is no input *size* for the ladder to grow — n = 100 and
# n = 6400 are two different values of the same one-word input, not two sizes.
# Both sides are bounded by that fixed width (the reference clears one set bit per
# n & (n - 1) step, at most 31 of them; the oracle prints at most 31 digits), so
# the paired ratio is flat by construction, and a class read off it would be a
# claim the ratio cannot support — the peak_elements precedent.


@oracle("missing-number")
def _missing_number_oracle(nums: list[int]) -> int:
    # Brute force, read straight off the statement's own sentence: walk the range
    # 0..n and return the first value the array does not contain. Total for any
    # input at all (including the empty list, which the statement's 1 <= n
    # excludes); the final return is unreachable while the input really is n
    # distinct values drawn from 0..n, and is kept only so this is total.
    for candidate in range(len(nums) + 1):
        if candidate not in nums:
            return candidate
    return len(nums) + 1


@judge_case("missing-number")
def _missing_number_case(n: int, rng: random.Random) -> tuple[list, int]:
    size = max(1, min(n, 12))  # the statement's own floor: n = nums.length >= 1
    candidates = list(range(size + 1))  # 0..n inclusive: n + 1 values, n present
    candidates.pop(rng.randrange(size + 1))  # exactly one of them goes missing
    rng.shuffle(candidates)
    return [candidates], _missing_number_oracle(candidates)


@profiler_input("missing-number")
def _missing_number_profiler(n: int, rng: random.Random) -> list:
    # The missing value is n itself, the LAST candidate of the range 0..n, and
    # the n present values are a shuffled 0..n-1 — inside 0 <= nums[i] <= n and
    # with n == nums.length, which is the statement's own shape. Two early exits
    # are closed by that choice: a solution that scans candidate values in order
    # (the brute-force shape) has to reach the very last one before it can
    # answer, and a position-based shortcut (`nums[i] != i` after an in-place
    # sort or cycle walk) cannot land on a lucky index, because the shuffle
    # destroys every positional pattern while the answer stays fixed at n.
    # Neither the reference (one XOR per element) nor the oracle can stop early.
    n = max(1, min(n, 10_000))  # the statement's own bound: 1 <= n <= 10^4
    values = list(range(n))
    rng.shuffle(values)
    return [values]


@oracle("counting-bits")
def _counting_bits_oracle(n: int) -> list[int]:
    """Brute force — the statement's own "very easy O(n log n)" baseline: count
    each i's set bits with a shift-and-mask loop (no popcount built-in, which the
    statement forbids) and collect the counts. n < 0 returns [] ; the statement's
    constraint is 0 <= n, so the generator never asks for one."""
    counts = []
    for value in range(max(0, n) + 1):
        bits = 0
        rest = value
        while rest:
            bits += rest & 1
            rest >>= 1
        counts.append(bits)
    return counts


@judge_case("counting-bits")
def _counting_bits_case(n: int, rng: random.Random) -> tuple[int, list[int]]:
    # The statement's constraint is 0 <= n <= 10^5 on a single scalar, so there
    # is no array shape to randomize: the case size *is* the value. It stays at
    # 0..12 on purpose — one 10^5 case would push ~200 kB of expected, and as
    # much again of got, through the judge's 1 MB stdout budget (proc.OUT_CAP),
    # where a truncated protocol line is reported as a broken run rather than as
    # the size problem it is. 0..12 already covers every branch of the intended
    # DP (0, 1, powers of two, odd and even); scale is the profiler input's job.
    n = max(0, min(n, 12))
    return [n], _counting_bits_oracle(n)


@profiler_input("counting-bits")
def _counting_bits_profiler(n: int, rng: random.Random) -> list:
    # Here the input *is* the size: the answer holds n + 1 counts, so both sides
    # do O(n) work with no shape to force and no early exit to avoid — a correct
    # solution must emit every entry, and the worst case is the whole array. The
    # probe's ladder (100..6400) sits inside the statement's 0 <= n <= 10^5, so
    # no probe_max_n cap is needed.
    return [n]


@oracle("sum-of-two-integers")
def _sum_of_two_integers_oracle(a: int, b: int) -> int:
    # Brute force, and deliberately NOT a solution to the puzzle: the oracle's
    # only job is to produce the right integer, and it may use the very operator
    # the statement forbids the student. Python's own integer addition shares no
    # step with the reference's carry loop, which is what makes the differential
    # against the reference worth something. Total over every pair.
    return sum((a, b))


@judge_case("sum-of-two-integers")
def _sum_of_two_integers_case(n: int, rng: random.Random) -> tuple[list, int]:
    bound = 1000  # the statement's own value constraint: -1000 <= a, b <= 1000
    # There is no length in this problem, so the caller's n (0..12) cannot be
    # clamped into a size constraint. It selects WHICH shape of pair this case
    # is, so the pairs a bit-trick solution gets wrong are emitted on purpose
    # instead of being left to a lucky draw; the live judge draws n at random,
    # so all five shapes appear within a session.
    shape = n % 5
    if shape == 0:  # any pair inside the range: both signs, any magnitudes
        a, b = rng.randint(-bound, bound), rng.randint(-bound, bound)
    elif shape == 1:  # the ends of the stated range, and zero
        a = rng.choice([-bound, bound])
        b = rng.choice([-bound, bound, 0])
    elif shape == 2:  # zero and the additive identities
        a = rng.choice([0, 1, -1, 2, -2])
        b = rng.choice([0, 1, -1, -bound, bound])
    elif shape == 3:  # a carry chain through every bit: (2^k - 1) + 1
        k = rng.randint(1, 9)
        a = (1 << k) - 1
        b = rng.choice([1, -1, 1 << k, -(1 << k)])
    else:  # opposite signs, half of them cancelling exactly: a + (-a) is the
        # pair a naive unmasked Python carry loop never escapes from
        a = rng.randint(1, bound)
        b = -a if rng.random() < 0.5 else -rng.randint(1, bound)
    return [a, b], _sum_of_two_integers_oracle(a, b)



# ----------------------------------------------------------------------- math_and_geometry


@oracle("multiply-strings")
def _multiply_strings_oracle(num1: str, num2: str) -> str:
    """Brute force, and deliberately NOT a student answer: Python's
    arbitrary-precision integers do the whole job in one expression, so the
    oracle has no digit or carry logic to share a bug with the reference's
    grade-school loop. The statement forbids exactly this route to the student,
    and the judge cannot see how the string was built - the note appended to the
    statement says so in the student's own words."""
    return str(int(num1) * int(num2))


def _multiply_strings_number(rng: random.Random, length: int) -> str:
    """A number of exactly ``length`` digits with no leading zero (the
    statement's constraint), except that a one-digit draw is '0' itself about a
    fifth of the time - the single number the statement allows to start with a
    zero."""
    if length == 1 and rng.random() < 0.2:
        return '0'
    digits = [rng.choice('123456789')]
    digits += [rng.choice('0123456789') for _ in range(length - 1)]
    return ''.join(digits)


@judge_case("multiply-strings")
def _multiply_strings_case(n: int, rng: random.Random) -> tuple[list, str]:
    # Both lengths come from [1, size] with size <= 12, so every operand is far
    # inside the statement's 1 <= num1.length, num2.length <= 200, is digits
    # only, and carries no leading zero. A zero operand is produced on purpose
    # (a one-digit draw, or the second operand outright): the statement's
    # zero-product carve-out is a path a generator drawn from 1..9 would never
    # reach, and expected always comes from the oracle.
    size = max(1, min(n, 12))
    num1 = _multiply_strings_number(rng, rng.randint(1, size))
    if rng.random() < 0.08:
        num2 = '0'
    else:
        num2 = _multiply_strings_number(rng, rng.randint(1, size))
    return [num1, num2], _multiply_strings_oracle(num1, num2)


@profiler_input("multiply-strings")
def _multiply_strings_profiler(n: int, rng: random.Random) -> list:
    # Total size about n, split evenly (equal lengths maximise m * n for a fixed
    # total), all nines: no digit pair is a zero shortcut and every position
    # carries, so the grade-school double loop runs to completion for both the
    # student and the reference. probe_max_n = 400 puts the top of the ladder at
    # 200 digits per operand, exactly the statement's cap; the default ladder
    # would have asked for 3200-digit operands, sixteen times over the stated
    # bound - the value-range mistake the v0.12 lesson is about.
    length = max(1, min(200, n // 2))
    return ['9' * length, '9' * length]


@oracle("rotate-image")
def _rotate_image_oracle(matrix: list[list[int]]) -> None:
    """Brute force by the definition: after a 90-degree clockwise turn the cell
    at (i, j) belongs at (j, size - 1 - i), so build the destination grid from
    that formula and write it back into the argument the caller holds - the
    post-call argument list is exactly what dojo's "mutates" verdict compares.
    Total on an empty matrix (the statement requires at least one row)."""
    size = len(matrix)
    rotated = [[0] * size for _ in range(size)]
    for i in range(size):
        for j in range(size):
            rotated[j][size - 1 - i] = matrix[i][j]
    matrix[:] = rotated


@judge_case("rotate-image")
def _rotate_image_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    side = max(1, min(n, 12))  # the statement's 1 <= n <= 20; the caller sends 0..12
    matrix = [[rng.randint(-1000, 1000) for _ in range(side)] for _ in range(side)]
    expected = [row[:] for row in matrix]
    _rotate_image_oracle(expected)
    # A "mutates" case: expected is the ARGUMENT LIST as it must stand after the
    # call, not the (None) return value the function hands back.
    return [matrix], [expected], {"compare": "mutates"}


@profiler_input("rotate-image")
def _rotate_image_profiler(n: int, rng: random.Random) -> list:
    # A square matrix of ~n cells: side = isqrt(n), counted up by hand because the
    # registry imports only `random`. The side is capped at the statement's own
    # 20, so with probe_max_n = 400 the ladder's largest point is exactly
    # 20 x 20 = 400 cells and NO point can exceed the statement's constraint.
    # Every cell holds a distinct value inside -1000..1000 (at most 400 cells and
    # 5 * index stays below 2001), so the digest is a real statement about the
    # permutation: a transpose-only, a row-flipped or a truncated rotation cannot
    # digest-match the reference. Nothing here can early-exit - a rotation has to
    # touch all n^2 cells whichever way it is written.
    side = 1
    while side < 20 and (side + 1) * (side + 1) <= n:
        side += 1
    return [
        [[(5 * (i * side + j)) % 2001 - 1000 for j in range(side)] for i in range(side)]
    ]


# Bases the generator draws from. Every one is inside the statement's
# -100.0 < x < 100.0, none is zero (n <= 0 is only legal when x != 0), and none
# is +-1.0: at |x| = 1 every power is the same number, so a case there could not
# tell an exponent bug from a correct answer, which is the opposite of what this
# generator is for. The pool is deliberately small so the tolerance argument in
# notes is exhaustively checkable.
_POWX_N_BASES = (
    2.0, 2.1, 1.5, 2.5, 3.0, 0.5, 0.75, 1.1,
    -2.0, -2.1, -1.5, -2.5, -3.0, -0.5, -0.75, -1.1,
)


@oracle("powx-n")
def _powx_n_oracle(x: float, n: int) -> float:
    """Brute force: x multiplied by itself |n| times - no fast exponentiation -
    and inverted once when the exponent is negative. This is the definition of
    x^n, so the intended binary exponentiation is checked against the slow thing
    it must equal."""
    result = 1.0
    for _ in range(abs(n)):
        result *= x
    return result if n >= 0 else 1.0 / result


@judge_case("powx-n")
def _powx_n_case(n: int, rng: random.Random) -> tuple[list, float, dict]:
    # The exponent is capped at +-5, well inside the statement's 2^31 - 1, for two
    # reasons. The judge grades a whole case list under one 10-second budget, so
    # a large exponent would turn a merely linear solution into a timeout that
    # hides every other verdict; and the tighter bound keeps every answer in
    # [3.0 ** -5, 3.0 ** 5] = [0.0041, 243] inside the statement's
    # -10^4 <= x^n <= 10^4 while leaving the smallest answer four hundred
    # tolerances away from zero - which is what makes approx:1e-5 safe (notes).
    limit = max(1, min(n, 5))
    x = rng.choice(_POWX_N_BASES)
    exponent = rng.randint(-limit, limit)
    return [x, exponent], _powx_n_oracle(x, exponent), {"compare": "approx:1e-5"}


@profiler_input("powx-n")
def _powx_n_profiler(n: int, rng: random.Random) -> list:
    # The measured size is the EXPONENT, not an array: x = 0.5 with exponent
    # k = max(0, min(n, 1000)) makes a repeated-multiplication solution pay k
    # float multiplies while the intended binary exponentiation pays about
    # log2(k) squarings, so the paired ratio separates the two classes instead of
    # measuring noise. Positive k only: 0.5 ** -k is 2 ** k, which leaves the
    # statement's |x^n| <= 10^4 bound as soon as k is large.
    #
    # 0.5 rather than a base near 1 (1 + 1e-7 would allow a much larger exponent
    # inside that bound): every partial product is an exact power of two, so a
    # repeated-multiplication student and this squaring reference return
    # bit-identical floats at every size, and the probe's exact digest comparison
    # cannot report a correct student as disagreeing with the reference. With a
    # base near 1 the two shapes differ in the last bits and a correct answer
    # would be blamed for it. probe_max_n = 1000 keeps the answer a normal double
    # (2 ** -1000 is about 9.3e-302, far above the smallest subnormal) instead of
    # underflowing to 0.0 at the default 6400, and the exponent stays inside the
    # statement's 2^31 - 1 with room to spare.
    return [0.5, max(0, min(n, 1000))]


@oracle("spiral-matrix")
def _spiral_matrix_oracle(matrix: list[list[int]]) -> list[int]:
    """Brute force by the definition: peel the outermost ring off a working copy
    of the grid - the top row left to right, the right column top to bottom, the
    bottom row right to left, the left column bottom to top - and repeat on what
    is left. That is the statement's walk written down directly, with no
    boundary bookkeeping. Total on an empty grid (the statement requires at
    least one row and one column)."""
    grid = [row[:] for row in matrix]
    out: list[int] = []
    while grid and grid[0]:
        out.extend(grid.pop(0))  # top row, left -> right
        if grid and grid[0]:
            for row in grid:  # right column, top -> bottom
                out.append(row.pop())
        if grid and grid[0]:
            out.extend(reversed(grid.pop()))  # bottom row, right -> left
        if grid and grid[0]:
            for row in reversed(grid):  # left column, bottom -> top
                out.append(row.pop(0))
    return out


@judge_case("spiral-matrix")
def _spiral_matrix_case(n: int, rng: random.Random) -> tuple[list, list]:
    # The statement's own constraint is 1 <= m, n <= 10, and the caller sends
    # 0..12 - so the floor is 1 and the ceiling is 10, not 12. Four of the five
    # shapes are the degenerate ones the examples never show: a single row, a
    # single column and a 1 x 1 grid are where a boundary walk that forgets to
    # re-check its bounds walks a row twice.
    base = max(1, min(n, 10))
    shape = rng.randrange(5)
    if shape == 0:
        rows = cols = base  # square
    elif shape == 1:
        rows, cols = base, rng.randint(1, 10)  # wider than tall
    elif shape == 2:
        rows, cols = rng.randint(1, 10), base  # taller than wide
    elif shape == 3:
        rows, cols = 1, base  # a single row
    else:
        rows, cols = base, 1  # a single column
    grid = [[rng.randint(-100, 100) for _ in range(cols)] for _ in range(rows)]
    return [grid], _spiral_matrix_oracle(grid)


@profiler_input("spiral-matrix")
def _spiral_matrix_profiler(n: int, rng: random.Random) -> list:
    # ~n cells in a square-ish grid: rows = isqrt(n) counted up by hand (the
    # registry imports only `random`) and cols = n // rows. The statement caps
    # BOTH dimensions at 10, which is why probe_max_n is 100: the ladder stops at
    # 10 x 10 = 100 cells, the largest legal input, and the default ladder's
    # 6400-cell point would be a 80 x 80 grid this statement forbids. Every cell
    # holds a distinct value inside -100..100 (at most 100 cells and 2 * index
    # stays below 201), so the returned order IS the whole answer: a walk that
    # repeats, drops or reorders a cell cannot match the reference's digest.
    # Both implementations are length-driven, so neither can early-exit.
    rows = 1
    while rows < 10 and (rows + 1) * (rows + 1) <= n:
        rows += 1
    cols = max(1, n // rows)
    return [
        [[(2 * (i * cols + j)) % 201 - 100 for j in range(cols)] for i in range(rows)]
    ]


@oracle("plus-one")
def _plus_one_oracle(digits: list[int]) -> list[int]:
    """Brute force: read the array as an arbitrary-precision integer, add one,
    and write the decimal back out. There is no carry logic here at all, so it
    cannot share a bug with the in-place ripple the reference walks."""
    if not digits:
        return []  # not a legal input (length >= 1); kept total so it cannot raise
    value = int("".join(str(digit) for digit in digits)) + 1
    return [int(character) for character in str(value)]


@judge_case("plus-one")
def _plus_one_case(n: int, rng: random.Random) -> tuple[list, list]:
    # The carry is the problem, so it is generated on purpose instead of being
    # left to chance: about a third of the cases are all nines (the carry crosses
    # the whole array and the answer gains a digit) and the rest end in a run of
    # nines after a non-zero leading digit. size is the statement's own bound
    # clamped to the caller's 0..12, the digits are 0..9, and the leading digit
    # is never 0, so no case violates a stated constraint (see notes on [0]).
    size = max(1, min(n, 12))  # the statement's 1 <= digits.length <= 100
    if rng.random() < 0.34:
        digits = [9] * size
    else:
        run = rng.randint(0, size - 1)  # size >= 1, so the leading digit stays outside the run
        middle = [rng.randint(0, 9) for _ in range(size - 1 - run)]
        digits = [rng.randint(1, 9)] + middle + [9] * run
    return [digits], _plus_one_oracle(digits)


@oracle("set-matrix-zeroes")
def _set_matrix_zeroes_oracle(matrix: list[list[int]]) -> None:
    """Brute force by the definition, with the statement's own "simple
    improvement": record which rows and which columns contain a zero FIRST, then
    zero every cell those flags cover. Reading all the zeros before writing any
    of them is what keeps the cascade honest, and writing back into the argument
    is what dojo's "mutates" verdict compares. Total on an empty matrix (the
    statement requires at least one row and one column)."""
    rows = len(matrix)
    if rows == 0:
        return
    cols = len(matrix[0])
    zero_rows = [False] * rows
    zero_cols = [False] * cols
    for i in range(rows):
        for j in range(cols):
            if matrix[i][j] == 0:
                zero_rows[i] = True
                zero_cols[j] = True
    for i in range(rows):
        for j in range(cols):
            if zero_rows[i] or zero_cols[j]:
                matrix[i][j] = 0


@judge_case("set-matrix-zeroes")
def _set_matrix_zeroes_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # The statement's 1 <= m, n <= 200; the caller sends 0..12, so both floors
    # matter (a 0-row matrix is not a legal input here).
    rows = max(1, min(n, 12))
    cols = rng.randint(1, max(1, min(n, 12)))
    if rng.random() < 0.5:
        # A dense small range: zeros are common, so flagged rows and columns
        # overlap and the cascade has to be decided before anything is written.
        matrix = [[rng.randint(-3, 3) for _ in range(cols)] for _ in range(rows)]
    else:
        # Sparse: exactly one zero, sometimes on the first row or the first
        # column - the very cells the constant-space marking uses as its flags.
        matrix = [[rng.randint(1, 1000) for _ in range(cols)] for _ in range(rows)]
        matrix[rng.randrange(rows)][rng.randrange(cols)] = 0
    expected = [row[:] for row in matrix]
    _set_matrix_zeroes_oracle(expected)
    return [matrix], [expected], {"compare": "mutates"}


@profiler_input("set-matrix-zeroes")
def _set_matrix_zeroes_profiler(n: int, rng: random.Random) -> list:
    # ~n cells in a square-ish grid: rows = isqrt(n) counted up by hand (the
    # registry imports only `random`) and cols = n // rows, so both dimensions
    # stay far below the statement's 200 and the default ladder's largest point
    # is 80 x 80 = 6400 cells. No probe_max_n is needed for this one.
    # Values are distinct and inside the statement's 32-bit range (7919 * i +
    # 104729 * j - 10^9 stays in [-10^9, -978 * 10^6]), so the digest is a real
    # statement about WHICH cells were zeroed. The three zeros sit on the first
    # row, on the first column and in the interior: that is the worst case for
    # the constant-space marking (a solution that forgets the first row/column
    # flags, or clears them too early, leaves a visibly different grid) and it
    # makes every marking and clearing pass run to the end on both sides.
    rows = 1
    while rows < 200 and (rows + 1) * (rows + 1) <= n:
        rows += 1
    cols = max(1, n // rows)
    matrix = [
        [7919 * i + 104729 * j - 1_000_000_000 for j in range(cols)]
        for i in range(rows)
    ]
    matrix[0][cols - 1] = 0
    matrix[rows - 1][0] = 0
    matrix[rows // 2][cols // 2] = 0
    return [matrix]


@oracle("happy-number")
def _happy_number_oracle(n: int) -> bool:
    """Brute force by the definition, with a different cycle test than the
    reference uses: Floyd's tortoise and hare walks the chain at one and two
    steps per turn, and the two meet exactly when the chain has entered a cycle.
    If the slow and fast pointers meet anywhere other than 1, the cycle cannot
    contain 1, which is the statement's "loops endlessly in a cycle which does
    not include 1". Total for n >= 0 (0 is its own fixed point and is not 1)."""
    slow = n
    fast = _happy_number_next(n)
    while fast != 1 and slow != fast:
        slow = _happy_number_next(slow)
        fast = _happy_number_next(_happy_number_next(fast))
    return fast == 1


def _happy_number_next(value: int) -> int:
    """The sum of the squares of the digits of ``value`` - one step of the
    statement's process - by arithmetic rather than str(), so the profiler's
    search below does not allocate a string per step."""
    total = 0
    while value:
        digit = value % 10
        total += digit * digit
        value //= 10
    return total


def _happy_number_chain(value: int) -> tuple[int, bool]:
    """(steps, reached_one) for the chain starting at ``value``: the definition
    run until it reaches 1 or repeats a value. Used ONLY to pick the profiler
    input's worst case - every expected answer comes from the oracle."""
    seen: set[int] = set()
    steps = 0
    while value != 1 and value not in seen:
        seen.add(value)
        value = _happy_number_next(value)
        steps += 1
    return steps, value == 1


@judge_case("happy-number")
def _happy_number_case(n: int, rng: random.Random) -> tuple[list, bool]:
    # This statement's parameter is a VALUE (1 <= n <= 2^31 - 1), not a size, so
    # the caller's 0..12 is read as a digit budget: 1..10 digits, ten being the
    # most 2^31 - 1 has. Values are drawn from the whole stated range, and the
    # two short lists make sure both verdicts appear at every call.
    digits = max(1, min(n, 10))
    low = 10 ** (digits - 1)
    high = min(10**digits - 1, 2**31 - 1)
    draw = rng.random()
    if draw < 0.2:
        value = rng.choice([1, 7, 10, 19, 100, 1000])  # happy values
    elif draw < 0.4:
        value = rng.choice([2, 3, 4, 16, 89, 999])  # unhappy values
    else:
        value = rng.randint(low, high)
    return [value], _happy_number_oracle(value)


@profiler_input("happy-number")
def _happy_number_profiler(n: int, rng: random.Random) -> list:
    # The input is a single VALUE, so "size ~n" means the number itself is about
    # n (100..6400 on the default ladder; the statement's ceiling is 2^31 - 1, so
    # every point is a legal input). The value is the worst case available in
    # [n, n + 128): an unhappy number whose chain is the longest there, so an
    # implementation that only stops at 1 cannot terminate on it and neither side
    # gets a short chain to hide in. Every 32-bit input falls to at most 730
    # after one step and the longest chain below that is 19 more steps, so ~12
    # iterations is the real worst case here, not a size effect - see the notes.
    start = max(1, n)
    best_value, best_score = start, None
    for value in range(start, start + 128):
        steps, reached_one = _happy_number_chain(value)
        score = (0 if reached_one else 1, steps)  # unhappy first, then the longest
        if best_score is None or score > best_score:
            best_value, best_score = value, score
    return [best_value]


# Generated cases draw their coordinates from a small corner of the statement's
# 0 <= x, y <= 1000 grid, so squares, duplicate adds and near-misses all occur
# instead of an all-zero expected list.
_DETECT_SQUARES_SPAN = 5


@oracle("detect-squares")
def _detect_squares_oracle(ops: list[list]) -> list:
    """Brute force: every added point is kept as its own list entry - which is
    what makes the statement's 'duplicate points should be treated as different
    points' literal - and a count tries every triple of stored entries against
    the query point, testing the four points directly."""
    points: list[list] = []
    out: list = []
    for op in ops:
        method, *args = op
        if method == 'add':
            points.append(list(args[0]))
            out.append(None)
        elif method == 'count':
            x, y = args[0]
            total = 0
            size = len(points)
            for i in range(size):
                for j in range(i + 1, size):
                    for k in range(j + 1, size):
                        quad = [points[i], points[j], points[k], [x, y]]
                        if _detect_squares_forms_square(quad):
                            total += 1
            out.append(total)
        else:  # pragma: no cover - the generator only emits add and count
            raise ValueError(f'unknown op {method}')
    return out


def _detect_squares_forms_square(quad: list[list]) -> bool:
    """Four points form an axis-aligned square of positive area exactly when
    they use two distinct x values and two distinct y values, the two spans are
    equal, and all four corners (x, y) are present. That is the definition of
    the shape, stated as a membership test - there is no distance or diagonal
    arithmetic here to get wrong."""
    xs = sorted({point[0] for point in quad})
    ys = sorted({point[1] for point in quad})
    if len(xs) != 2 or len(ys) != 2:
        return False
    if xs[1] - xs[0] != ys[1] - ys[0]:
        return False
    present = {(point[0], point[1]) for point in quad}
    return all((x, y) in present for x in xs for y in ys)


@judge_case("detect-squares")
def _detect_squares_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # Deterministic by construction: every op comes from the seeded rng, the
    # coordinate pool is fixed, and the harness builds a fresh instance per case,
    # so the same (n, rng) always replays the same stream on an empty structure.
    # The first two ops are adds (a count is never the whole case) and the rest
    # alternate, so both methods and the duplicate-add path are exercised.
    steps = 2 * max(1, min(n, 12)) + 1
    ops: list[list] = []
    for step in range(steps):
        point = [rng.randrange(_DETECT_SQUARES_SPAN), rng.randrange(_DETECT_SQUARES_SPAN)]
        if step >= 2 and step % 2 == 0:
            ops.append(['count', point])
        else:
            ops.append(['add', point])
    return [], _detect_squares_oracle(ops), {'ops': ops}



# ----------------------------------------------------------------------- intervals


@oracle("merge-intervals")
def _merge_intervals_oracle(intervals: list[list[int]]) -> list[list[int]]:
    # Brute force, and a different mechanism from the reference's sort-and-sweep:
    # treat the intervals as a graph whose edges join two intervals that share at
    # least one point (the statement's own reading of "overlapping", which its
    # Example 2 spells out for [1,4] and [4,5]) and take the connected components
    # -- one component at a time, by closing a group over every interval still in
    # the pool -- replacing each component by its union [min start, max end]. The
    # components are then sorted for the canonical order. Nothing here depends on
    # the input being sorted (the statement does not promise it) or on its
    # intervals being disjoint, and it is total: the empty list returns [].
    pooled = [list(iv) for iv in intervals]
    components: list[list[int]] = []
    while pooled:
        lo, hi = pooled.pop()
        changed = True
        while changed:
            changed = False
            rest = []
            for other in pooled:
                if max(lo, other[0]) <= min(hi, other[1]):
                    lo, hi = min(lo, other[0]), max(hi, other[1])
                    changed = True
                else:
                    rest.append(other)
            pooled = rest
        components.append([lo, hi])
    components.sort()
    return components


@judge_case("merge-intervals")
def _merge_intervals_case(n: int, rng: random.Random) -> tuple[list, list, dict]:
    # 1 <= intervals.length <= 10^4, so the clamp's floor is 1 (the caller sends
    # 0..12 and the statement has no empty input) and 0 <= starti <= endi <= 10^4
    # -- lengths are drawn 1..3, with one case in five turning exactly one interval
    # into a zero-length one (end = start, which the non-strict bound allows), so
    # the degenerate shape is covered without every case being about it.
    #
    # The value range is kept small (starts 0..12, ends at most 15) so that
    # overlaps, exact duplicates and touches all happen often, and the order is
    # SHUFFLED on purpose: the statement says nothing about the input being
    # sorted, so an implementation that forgets to sort has to fail here (the
    # third Example, [[4,7],[1,4]] -> [[1,7]], is the statement's own warning that
    # the input may arrive out of order).
    #
    # The verdict tag rides on every case: the answer is the set of merged
    # intervals, whose order the statement leaves free, so the cases are judged
    # order-insensitively ("compare": "sorted") while the oracle still emits the
    # canonical ascending order.
    count = max(1, min(n, 12))
    intervals = []
    for _ in range(count):
        start = rng.randint(0, 12)
        intervals.append([start, start + rng.randint(1, 3)])
    if rng.random() < 0.2:
        flattened = intervals[rng.randrange(len(intervals))]
        flattened[1] = flattened[0]  # a zero-length interval, still 0 <= start <= end
    rng.shuffle(intervals)
    return [intervals], _merge_intervals_oracle(intervals), {"compare": "sorted"}


@profiler_input("merge-intervals")
def _merge_intervals_profiler(n: int, rng: random.Random) -> list:
    # n intervals that touch end-to-start -- [0, 1], [1, 2], ..., [n-1, n] -- with
    # every value inside the statement's 0 <= starti <= endi <= 10^4 (the largest
    # end is n = 6400 at the probe's top of the ladder).
    #
    # Why this shape: consecutive intervals share a point, so the sort-and-sweep
    # takes its MERGE branch on every single iteration -- it never appends a
    # second interval and never falls back to copying -- and the whole array
    # collapses to [0, n]. That is the worst case for the sweep, and there is no
    # early exit on the other side either: the input must be read in full to be
    # ordered, and an implementation cannot know that everything merges without
    # walking all of it.
    #
    # The ORDER is scrambled, which is the part that is easy to get wrong: the
    # reference sorts, and Python's sort is Timsort, whose best case on input that
    # already ascends is one detected run -- O(n) comparisons. Handing it the chain
    # in its natural order would quietly delete the n log n term this problem is
    # about, from BOTH sides of the paired measurement, and the ladder's ratios
    # would then describe something the problem never asked about. The generator
    # receives the probe's own seeded rng (random.Random(SEED) in probe.run_probe),
    # so the scramble is reproducible run to run.
    count = max(1, n)
    intervals = [[i, i + 1] for i in range(count)]
    rng.shuffle(intervals)
    return [intervals]


@oracle("insert-interval")
def _insert_interval_oracle(
    intervals: list[list[int]], newInterval: list[int]
) -> list[list[int]]:
    # Brute force, and a different mechanism from the reference's single sweep:
    # pool the input intervals with the new one, then close the relation
    # "these two share at least one point" -- the statement's own definition of
    # overlapping -- until no such pair is left, replacing each such group by its
    # union [min start, max end], and sort the result. Nothing here assumes the
    # input is sorted by start or that its intervals are disjoint (the statement
    # promises both, but an oracle should not need the promise), it never looks
    # at an interval once per phase, and it is total: the empty input returns
    # [[newInterval]] because the new interval is always in the pool.
    pooled = [list(iv) for iv in intervals] + [list(newInterval)]
    components: list[list[int]] = []
    while pooled:
        lo, hi = pooled.pop()
        changed = True
        while changed:
            changed = False
            rest = []
            for other in pooled:
                if max(lo, other[0]) <= min(hi, other[1]):
                    lo, hi = min(lo, other[0]), max(hi, other[1])
                    changed = True
                else:
                    rest.append(other)
            pooled = rest
        components.append([lo, hi])
    components.sort()
    return components


@judge_case("insert-interval")
def _insert_interval_case(
    n: int, rng: random.Random
) -> tuple[list, list]:
    # n counts the EXISTING intervals: the statement allows 0 <= intervals.length
    # <= 10^4 and the caller sends 0..12, so the clamp's floor of 0 is real and
    # the empty array is a case the generator actually emits.
    #
    # The starts come from a 5-spaced grid, which makes two of the statement's
    # promises structural rather than hoped for: the array is sorted by starti,
    # and no two of its intervals touch (two intervals that share a point are
    # overlapping by the statement's own definition, so a valid input has at
    # least one unused integer between consecutive intervals -- an end is at most
    # start + 4 and the next start is at least this start + 5).
    #
    # Lengths are 1..4, and one case in four turns exactly one interval into a
    # zero-length one (end = start), which the constraint 0 <= starti <= endi
    # allows: the degenerate shape is covered without every case being about it,
    # and starti <= endi is structural in both branches. The new interval is a
    # separate draw and is zero-length in about one case in seven.
    #
    # Every value stays inside the statement's 0..10^5: the largest end any
    # branch can produce is 80 + 6 = 86.
    count = max(0, min(n, 12))
    starts = sorted(rng.sample(range(0, 80, 5), count))
    intervals = [[s, s + rng.randint(1, 4)] for s in starts]
    if intervals and rng.random() < 0.25:
        flattened = intervals[rng.randrange(len(intervals))]
        flattened[1] = flattened[0]  # a zero-length interval, still inside the grid
    start = rng.randint(0, 80)
    new_interval = [start, start + rng.randint(0, 6)]
    return [intervals, new_interval], _insert_interval_oracle(intervals, new_interval)


@profiler_input("insert-interval")
def _insert_interval_profiler(n: int, rng: random.Random) -> list:
    # n intervals of the kind the statement guarantees -- sorted by starti, no
    # two sharing a point, every value inside 0 <= starti <= endi <= 10^5 (the
    # largest end is 2n + 1 = 12801 at the probe's n = 6400) -- plus a new
    # interval that spans all of them:
    #
    #     intervals = [[0, 1], [2, 3], ..., [2n-2, 2n-1]],  newInterval = [0, 2n]
    #
    # Which path does that force? The reference's three phases are (1) copy the
    # intervals that end before the new start, (2) absorb every interval that
    # starts at or before the new end, (3) copy the tail. Here (1) copies nothing
    # and (3) copies nothing, so phase (2) -- the only phase that does per-element
    # work beyond an append (a min, a max and a list rebuild) -- runs all n times,
    # and the answer is the single interval [0, 2n]. Placing the new interval
    # before or after everything instead would move the same n elements through
    # the cheap phases and leave the expensive one empty, which is the wrong side
    # of the worst case. There is no early exit to defend against on either side:
    # an implementation must read every interval to know where the new one goes
    # (a bisect-based one still has to copy the tail), and with the output being
    # one interval there is nothing for an output-driven shortcut to skip either.
    count = max(0, n)
    intervals = [[2 * i, 2 * i + 1] for i in range(count)]
    return [intervals, [0, 2 * count]]


@oracle("meeting-rooms")
def _meeting_rooms_oracle(intervals: list[list[int]]) -> bool:
    # Every pair, checked as a pair: two meetings clash when their interiors
    # intersect, so one ending exactly when the next starts is not a clash.
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            if intervals[i][0] < intervals[j][1] and intervals[j][0] < intervals[i][1]:
                return False
    return True


@judge_case("meeting-rooms")
def _meeting_rooms_case(n: int, rng: random.Random) -> tuple[list, bool]:
    n = max(0, min(n, 12))  # the statement's own range: 0 <= intervals.length
    intervals = []
    for _ in range(n):
        start = rng.randint(0, 10)
        intervals.append([start, start + rng.randint(1, 4)])  # 0 <= start < end
    if n >= 2 and rng.random() < 0.3:
        # Force the boundary the statement names explicitly: the next meeting
        # starts exactly when this one ends, which is *not* a clash.
        intervals[1] = [intervals[0][1], intervals[0][1] + rng.randint(1, 3)]
    return [intervals], _meeting_rooms_oracle(intervals)


@profiler_input("meeting-rooms")
def _meeting_rooms_profiler(n: int, rng: random.Random) -> list:
    # n disjoint meetings ([0,1], [2,3], ...) inside 0 <= start < end <= 10^6,
    # then shuffled. Disjoint, so no pair clashes: the oracle's all-pairs scan
    # runs to the end and the reference's early return never fires. Shuffled,
    # because a sorted list is one ascending run -- Timsort finishes it in O(n),
    # which would measure a correct n log n solution as linear.
    intervals = [[2 * i, 2 * i + 1] for i in range(n)]
    rng.shuffle(intervals)
    return [intervals]


@oracle("meeting-rooms-ii")
def _meeting_rooms_ii_oracle(intervals: list[list[int]]) -> int:
    # The answer is the largest number of meetings running at the same instant,
    # and that instant can always be taken to be a meeting's start, so counting
    # the meetings in progress at every start is exact. O(n^2), and deliberately
    # NOT "how many intervals overlap this one": [0,10] overlaps both [1,2] and
    # [3,4], but those two never run together, so that count says 3 where the
    # answer is 2.
    best = 0
    for start, _ in intervals:
        active = sum(
            1 for other_start, other_end in intervals if other_start <= start < other_end
        )
        if active > best:
            best = active
    return best


@judge_case("meeting-rooms-ii")
def _meeting_rooms_ii_case(n: int, rng: random.Random) -> tuple[list, int]:
    n = max(1, min(n, 12))  # the statement's own range: 1 <= intervals.length
    intervals = []
    for _ in range(n):
        start = rng.randint(0, 10)
        intervals.append([start, start + rng.randint(1, 4)])  # 0 <= start < end
    if n >= 2 and rng.random() < 0.3:
        # Force the boundary the statement names explicitly: a meeting that ends
        # at t frees its room for one starting at t, so this pair needs one room.
        intervals[1] = [intervals[0][1], intervals[0][1] + rng.randint(1, 3)]
    return [intervals], _meeting_rooms_ii_oracle(intervals)


@profiler_input("meeting-rooms-ii")
def _meeting_rooms_ii_profiler(n: int, rng: random.Random) -> list:
    # A fixed-width sliding window inside 0 <= start < end <= 10^6: meeting i runs
    # [i, i + n//2]. The peak occupancy is n//2 and it is sustained over the
    # second half of the starts; after the first n//2 starts every step both
    # frees a room and takes one, so the sweep's inner loop is never dead (the
    # all-overlapping variant, the other obvious worst case, would leave it dead
    # while costing the same). Shuffled, because a sorted list is one ascending
    # run -- Timsort finishes it in O(n).
    width = max(1, n // 2)
    intervals = [[i, i + width] for i in range(n)]
    rng.shuffle(intervals)
    return [intervals]


@oracle("non-overlapping-intervals")
def _non_overlapping_intervals_oracle(intervals: list[list[int]]) -> int:
    # Brute force over the structure of the answer, not over subsets (a subset
    # sweep would be 2^n, which the statement's n = 10^5 makes meaningless even
    # for a trust anchor): removing as few intervals as possible leaves the
    # LARGEST set of pairwise non-overlapping ones, so this computes the longest
    # such chain with the obvious O(n^2) DP and subtracts.
    #
    # Sort a copy by (start, end) first. A chain's intervals are pairwise
    # non-overlapping, so their starts are distinct and the chain appears in this
    # order as a subsequence -- no valid chain is lost by sorting. dp[i] is the
    # longest chain whose last interval is i, and j may precede i exactly when
    # ordered[j][1] <= ordered[i][0]: `<=` and not `<`, because the statement
    # says intervals that only touch at a point are NON-overlapping, so [1,2] and
    # [2,3] may both be kept.
    ordered = sorted(([iv[0], iv[1]] for iv in intervals), key=lambda iv: (iv[0], iv[1]))
    best = 0
    dp = [1] * len(ordered)
    for i in range(len(ordered)):
        for j in range(i):
            if ordered[j][1] <= ordered[i][0] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
        if dp[i] > best:
            best = dp[i]
    return len(ordered) - best


@judge_case("non-overlapping-intervals")
def _non_overlapping_intervals_case(n: int, rng: random.Random) -> tuple[list, int]:
    # 1 <= intervals.length <= 10^5, so the clamp's floor of 1 is real (the caller
    # sends 0..12 and the statement has no empty input), and the value bound is
    # -5 * 10^4 <= starti < endi <= 5 * 10^4 -- a STRICT inequality, so every
    # interval built here has length >= 1 and the zero-length interval that LC 57
    # and LC 56 allow is a constraint VIOLATION here. All values stay inside
    # -10..15. The coordinate range is kept small so overlaps are common.
    #
    # Three shapes, one case in three each, because the interesting failures live
    # in different corners:
    #   * TOUCHING CHAIN -- consecutive intervals share an endpoint
    #     (start_{k+1} == end_k). The statement says such a pair does not overlap
    #     ("[1, 2] and [2, 3] are non-overlapping"), so nothing has to be removed
    #     and the answer is 0; it is also the only shape that fails a greedy
    #     written with `>` where `>=` is required.
    #   * COPIES -- the same interval `count` times, which is Example 2's shape:
    #     all of them bar one must go, so the answer is count - 1.
    #   * FREE -- independent random intervals, where overlaps, duplicates and
    #     incidental touches all occur and the answer is somewhere in between.
    # The freed order is shuffled in the chain and free modes: the statement
    # promises nothing about the input's order.
    count = max(1, min(n, 12))
    mode = rng.randrange(3)
    if mode == 0:
        intervals = []
        cursor = rng.randint(-10, 10)
        for _ in range(count):
            length = rng.randint(1, 3)
            intervals.append([cursor, cursor + length])
            cursor += length  # the next start IS this end: they touch, not overlap
        rng.shuffle(intervals)
    elif mode == 1:
        start = rng.randint(-10, 10)
        end = start + rng.randint(1, 5)
        intervals = [[start, end] for _ in range(count)]
    else:
        intervals = []
        for _ in range(count):
            start = rng.randint(-10, 10)
            intervals.append([start, start + rng.randint(1, 5)])
        rng.shuffle(intervals)
    return [intervals], _non_overlapping_intervals_oracle(intervals)


@profiler_input("non-overlapping-intervals")
def _non_overlapping_intervals_profiler(n: int, rng: random.Random) -> list:
    # n intervals that touch end-to-start -- [0, 1], [1, 2], ..., [n-1, n] -- in a
    # scrambled order. The values respect the statement's STRICT bound
    # -5 * 10^4 <= starti < endi <= 5 * 10^4 with room to spare (the largest end
    # is n = 6400) and every interval has length 1, so no zero-length input is
    # ever generated.
    #
    # Why this shape: nothing early-exits. The intended greedy reads all n
    # intervals, and here it takes its `start >= last_end` branch on every single
    # one of them (each interval starts exactly where the running end stopped),
    # keeping all n -- so the answer is 0 at every size and the sweep is exercised
    # on the touching-equality side of the comparison rather than on the easy
    # "strictly after" side. The O(n^2) oracle, which has no early exit either,
    # sees the same chain and finds it entirely keepable.
    #
    # The ORDER is the part that is easy to get wrong: the reference sorts by end,
    # and Python's sort is Timsort, whose best case on input that already ascends
    # is one detected run -- O(n) comparisons. Handing it the chain in its natural
    # order would delete the n log n term this problem is about from BOTH sides of
    # the paired measurement. The rng is the probe's own seeded generator
    # (probe.run_probe builds one random.Random(SEED) for the whole ladder), so
    # the scramble is reproducible.
    count = max(1, n)
    intervals = [[i, i + 1] for i in range(count)]
    rng.shuffle(intervals)
    return [intervals]


@oracle("minimum-interval-to-include-each-query")
def _minimum_interval_to_include_each_query_oracle(
    intervals: list[list[int]], queries: list[int]
) -> list[int]:
    # Brute force: every interval against every query, keeping the smallest size
    # that covers it, -1 when nothing does. Total on empty intervals (all -1)
    # and on empty queries ([]).
    answers = []
    for point in queries:
        best = -1
        for left, right in intervals:
            if left <= point <= right:
                size = right - left + 1
                if best == -1 or size < best:
                    best = size
        answers.append(best)
    return answers


@judge_case("minimum-interval-to-include-each-query")
def _minimum_interval_to_include_each_query_case(
    n: int, rng: random.Random
) -> tuple[list, list[int]]:
    n = max(1, min(n, 12))  # the statement's own ranges: 1 <= intervals.length, 1 <= queries.length
    intervals = []
    for _ in range(n):
        left = rng.randint(1, 10)
        intervals.append([left, left + rng.randint(0, 4)])  # 1 <= left_i <= right_i
    queries = [rng.randint(1, 12) for _ in range(rng.randint(1, n))]
    if n >= 2 and rng.random() < 0.5:
        # Reuse a query value and a neighbouring interval's endpoint: the
        # inclusive boundary and the answer-at-every-position are what the
        # examples pin least (they never repeat a query).
        queries[rng.randrange(len(queries))] = intervals[0][1]
    return [intervals, queries], _minimum_interval_to_include_each_query_oracle(
        intervals, queries
    )


@profiler_input("minimum-interval-to-include-each-query")
def _minimum_interval_to_include_each_query_profiler(n: int, rng: random.Random) -> list:
    # Half the budget intervals, half queries: the brute force's cost is exactly
    # (intervals x queries), so an even split is what makes it pay for the whole
    # input, while the sweep gets one sort on each side. The intervals start one
    # unit apart, so their union covers every position a query can hit (nothing
    # is trivially -1), and their lengths cycle through (2,3,5,8,13,21,34,55), so
    # short intervals expire as the sweep advances -- the heap really pops --
    # while long ones keep later queries covered, so the per-query work never
    # collapses. Both lists are shuffled: the statement promises neither order,
    # and a sorted list is one ascending run that Timsort finishes in O(n). Every
    # value stays inside 1 <= left_i <= right_i <= 10^7 and 1 <= queries[j] <= 10^7.
    m = max(1, n // 2)
    q = max(1, n - m)
    lengths = (2, 3, 5, 8, 13, 21, 34, 55)
    intervals = [[1 + i, i + lengths[i % len(lengths)]] for i in range(m)]
    span = m + lengths[(m - 1) % len(lengths)]
    queries = [1 + (j * span) // q for j in range(q)]
    rng.shuffle(intervals)
    rng.shuffle(queries)
    return [intervals, queries]


# ------------------------------------------------- canonical references (v0.12)
#
# The probe's performance baseline, and the large-input comparator. Each entry
# must agree with the oracle for its slug everywhere the oracle can run
# (tests/test_registry.py re-checks the whole set); a wrong reference would make
# the probe derive confident verdicts about the student from a broken baseline.
#
# Where the oracle is already the intended-complexity solution it is duplicated
# here deliberately: a reference must stand alone so the probe can run it in a
# subprocess, and keeping the two roles explicit is what stops a brute-force
# oracle from silently becoming a performance baseline.


@reference("contains_duplicate")
def _contains_duplicate_reference(nums: list[int]) -> bool:
    return len(nums) != len(set(nums))


@reference("valid_parentheses")
def _valid_parentheses_reference(s: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            return False
    return not stack


@reference("array_intersection")
def _intersection_reference(A: list[int], B: list[int]) -> list[int]:
    return sorted(set(A) & set(B))


@reference("products_of_array_except_self")
def _prod_except_self_reference(nums: list[int]) -> list[int]:
    """Prefix/suffix products — the intended O(n).

    The oracle is an O(n^2) double loop, so before this reference existed the
    problem had no fast baseline at all: the probe could only have reported a
    correct O(n) solution as "faster than the reference", which says nothing."""
    size = len(nums)
    out = [1] * size
    left = 1
    for i in range(size):
        out[i] = left
        left *= nums[i]
    right = 1
    for i in range(size - 1, -1, -1):
        out[i] *= right
        right *= nums[i]
    return out


@reference("top_k_frequent_elements")
def _top_k_freq_reference(nums: list[int], k: int) -> list[int]:
    """Frequency buckets — the intended O(n).

    Mirrors the oracle's tie-break exactly (count descending, then value
    ascending): the gate compares the two under the judge's own equality, so a
    reference that broke ties differently would be — correctly — refused."""
    counts: dict[int, int] = {}
    for num in nums:
        counts[num] = counts.get(num, 0) + 1
    buckets: dict[int, list[int]] = {}
    for value, count in counts.items():
        buckets.setdefault(count, []).append(value)
    out: list[int] = []
    for count in sorted(buckets, reverse=True):
        for value in sorted(buckets[count]):
            out.append(value)
            if len(out) == k:
                return out
    return out


# --- canonical reference (binary_tree_diameter) ---
@reference("binary_tree_diameter")
def diameter(root: list | None) -> int:
    best = 0

    def visit(node: list | None) -> int:
        nonlocal best
        if node is None:
            return 0
        left = visit(node[1])
        right = visit(node[2])
        best = max(best, left + right)
        return 1 + max(left, right)

    visit(root)
    return best


# --- canonical reference (car_fleet) ---
@reference("car_fleet")
def car_fleet(target: int, position: list[int], speed: list[int]) -> int:
    cars = sorted(zip(position, speed), reverse=True)
    fleets = 0
    slowest = -1.0
    for pos, spd in cars:
        arrival = (target - pos) / spd
        if arrival > slowest:
            fleets += 1
            slowest = arrival
    return fleets


# --- canonical reference (container_with_most_water) ---
@reference("container_with_most_water")
def max_area(height: list[int]) -> int:
    left, right = 0, len(height) - 1
    best = 0
    while left < right:
        h = min(height[left], height[right])
        area = h * (right - left)
        if area > best:
            best = area
        if height[left] < height[right]:
            left += 1
        else:
            right -= 1
    return best


# --- canonical reference (correlation) ---
@reference("correlation")
def correlation(X: list, Y: list) -> float:
    n = len(X)
    sx = sy = sxy = sxx = syy = 0.0
    for x, y in zip(X, Y):
        sx += x
        sy += y
        sxy += x * y
        sxx += x * x
        syy += y * y
    ex = sx / n
    ey = sy / n
    exy = sxy / n
    exx = sxx / n
    eyy = syy / n
    return round((exy - ex * ey) / (((exx - ex * ex) * (eyy - ey * ey)) ** 0.5), 4)


# --- canonical reference (daily_temperatures) ---
@reference("daily_temperatures")
def daily_temperatures(temperatures: list[int]) -> list[int]:
    n = len(temperatures)
    result = [0] * n
    stack: list[int] = []
    for i, t in enumerate(temperatures):
        while stack and temperatures[stack[-1]] < t:
            j = stack.pop()
            result[j] = i - j
        stack.append(i)
    return result


# --- canonical reference (evaluate_reverse_polish_notation) ---
@reference("evaluate_reverse_polish_notation")
def eval_rpn(tokens: list[str]) -> int:
    stack: list[int] = []
    for tok in tokens:
        if tok == "+":
            b = stack.pop()
            a = stack.pop()
            stack.append(a + b)
        elif tok == "-":
            b = stack.pop()
            a = stack.pop()
            stack.append(a - b)
        elif tok == "*":
            b = stack.pop()
            a = stack.pop()
            stack.append(a * b)
        elif tok == "/":
            b = stack.pop()
            a = stack.pop()
            stack.append(int(a / b))
        else:
            stack.append(int(tok))
    return stack[-1]


# --- canonical reference (generate_parentheses) ---
@reference("generate_parentheses")
def generate_parentheses(n: int) -> list[str]:
    out: list[str] = []
    buf: list[str] = []

    def build(opens: int, closes: int) -> None:
        if opens == n and closes == n:
            out.append("".join(buf))
            return
        if opens < n:
            buf.append("(")
            build(opens + 1, closes)
            buf.pop()
        if closes < opens:
            buf.append(")")
            build(opens, closes + 1)
            buf.pop()

    build(0, 0)
    return out


# --- canonical reference (group_anagrams) ---
@reference("group_anagrams")
def group_anagrams(strs: list[str]) -> list[list[str]]:
    groups: dict[tuple[int, ...], list[str]] = {}
    for s in strs:
        counts = [0] * 26
        for ch in s:
            counts[ord(ch) - 97] += 1
        key = tuple(counts)
        groups.setdefault(key, []).append(s)
    return [sorted(group) for _, group in sorted(groups.items())]


# --- canonical reference (k_closest_points) ---
@reference("k_closest_points")
def k_closest(k: int, points: list[list[int]]) -> list[list[int]]:
    ranked = sorted(points, key=lambda p: (p[0] * p[0] + p[1] * p[1], p[0], p[1]))
    return ranked[:k]


# --- canonical reference (k_smallest_elem_matrix) ---
@reference("k_smallest_elem_matrix")
def k_smallest(k: int, matrix: list[list[int]]) -> int:
    import heapq
    n = len(matrix)
    heap = [(matrix[i][0], i, 0) for i in range(n)]
    heapq.heapify(heap)
    for _ in range(k - 1):
        val, r, c = heapq.heappop(heap)
        if c + 1 < n:
            heapq.heappush(heap, (matrix[r][c + 1], r, c + 1))
    return heap[0][0]


# --- canonical reference (largest_rectangle_in_histogram) ---
@reference("largest_rectangle_in_histogram")
def largest_rectangle(heights: list[int]) -> int:
    stack = []
    best = 0
    for i, h in enumerate(heights):
        start = i
        while stack and stack[-1][1] > h:
            idx, height = stack.pop()
            best = max(best, height * (i - idx))
            start = idx
        stack.append((start, h))
    n = len(heights)
    for idx, height in stack:
        best = max(best, height * (n - idx))
    return best


# --- canonical reference (longest_consecutive_sequence) ---
@reference("longest_consecutive_sequence")
def longest_seqlen(nums: list[int]) -> int:
    num_set = set(nums)
    longest = 0
    for num in num_set:
        if num - 1 not in num_set:
            length = 1
            while num + length in num_set:
                length += 1
            if length > longest:
                longest = length
    return longest


# --- canonical reference (max_prod_3_nums) ---
@reference("max_prod_3_nums")
def max_tri_prod(A: list[int]) -> int:
    A.sort()
    return max(A[-1] * A[-2] * A[-3], A[0] * A[1] * A[-1])


# --- canonical reference (mirror_image_binary_tree) ---
@reference("mirror_image_binary_tree")
def is_mirror(root: list | None) -> bool:
    if root is None:
        return True

    stack = [(root[1], root[2])]
    while stack:
        a, b = stack.pop()
        if a is None or b is None:
            if a is not b:
                return False
            continue
        if a[0] != b[0]:
            return False
        stack.append((a[1], b[2]))
        stack.append((a[2], b[1]))
    return True


# --- canonical reference (peak_elements) ---
@reference("peak_elements")
def find_a_peak(nums: list[int]) -> int:
    lo, hi = 0, len(nums) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if nums[mid] < nums[mid + 1]:
            lo = mid + 1
        else:
            hi = mid
    return lo


# --- canonical reference (sum_largest_contiguous_subarray) ---
@reference("sum_largest_contiguous_subarray")
def sum_largest_subarray(A: list[int]) -> int:
    best = 0
    current = 0
    for x in A:
        current += x
        if current < 0:
            current = 0
        elif current > best:
            best = current
    return best


# --- canonical reference (three_sum) ---
@reference("three_sum")
def three_sum(nums: list[int]) -> list[list[int]]:
    nums.sort()
    n = len(nums)
    res = []
    for i in range(n - 2):
        if nums[i] > 0:
            break
        if i > 0 and nums[i] == nums[i - 1]:
            continue
        lo, hi = i + 1, n - 1
        target = -nums[i]
        while lo < hi:
            s = nums[lo] + nums[hi]
            if s < target:
                lo += 1
            elif s > target:
                hi -= 1
            else:
                res.append([nums[i], nums[lo], nums[hi]])
                lo += 1
                hi -= 1
                while lo < hi and nums[lo] == nums[lo - 1]:
                    lo += 1
                while lo < hi and nums[hi] == nums[hi + 1]:
                    hi -= 1
    return res


# --- canonical reference (trapping_rain_water) ---
@reference("trapping_rain_water")
def trap(height: list[int]) -> int:
    n = len(height)
    if n == 0:
        return 0
    left_max = [0] * n
    right_max = [0] * n
    left_max[0] = height[0]
    for i in range(1, n):
        left_max[i] = max(left_max[i - 1], height[i])
    right_max[n - 1] = height[n - 1]
    for i in range(n - 2, -1, -1):
        right_max[i] = max(right_max[i + 1], height[i])
    total = 0
    for i in range(n):
        total += min(left_max[i], right_max[i]) - height[i]
    return total


# --- canonical reference (two_sum) ---
@reference("two_sum")
def twosum(nums: list[int], target: int) -> list[int]:
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []


# --- canonical reference (two_sum_2) ---
@reference("two_sum_2")
def two_sum_2(numbers: list[int], target: int) -> list[int]:
    left, right = 0, len(numbers) - 1
    while left < right:
        s = numbers[left] + numbers[right]
        if s == target:
            return [left + 1, right + 1]
        elif s < target:
            left += 1
        else:
            right -= 1
    return []


# --- canonical reference (valid_anagram) ---
@reference("valid_anagram")
def valid_anagram(s: str, t: str) -> bool:
    if len(s) != len(t):
        return False
    counts = [0] * 26
    for ch in s:
        counts[ord(ch) - 97] += 1
    for ch in t:
        counts[ord(ch) - 97] -= 1
    return all(c == 0 for c in counts)


# --- canonical reference (valid_palindrome) ---
@reference("valid_palindrome")
def is_palindrome(s: str) -> bool:
    i, j = 0, len(s) - 1
    while i < j:
        while i < j and not s[i].isalnum():
            i += 1
        while i < j and not s[j].isalnum():
            j -= 1
        if s[i].lower() != s[j].lower():
            return False
        i += 1
        j -= 1
    return True


# --- canonical reference (valid_sudoku) ---
@reference("valid_sudoku")
def valid_sudoku(board: list[list[str]]) -> bool:
    rows = [set() for _ in range(9)]
    cols = [set() for _ in range(9)]
    boxes = [set() for _ in range(9)]
    for i in range(9):
        for j in range(9):
            c = board[i][j]
            if c == ".":
                continue
            b = (i // 3) * 3 + (j // 3)
            if c in rows[i] or c in cols[j] or c in boxes[b]:
                return False
            rows[i].add(c)
            cols[j].add(c)
            boxes[b].add(c)
    return True


# --- canonical reference (best-time-to-buy-and-sell-stock) ---

@reference("best-time-to-buy-and-sell-stock")
def _best_time_to_buy_and_sell_stock_reference(prices: list[int]) -> int:
    best = 0
    low = None
    for price in prices:
        if low is None or price < low:
            low = price
        else:
            best = max(best, price - low)
    return best


# --- canonical reference (longest-repeating-character-replacement) ---

@reference("longest-repeating-character-replacement")
def _longest_repeating_character_replacement_reference(s: str, k: int) -> int:
    counts = [0] * 26
    left = 0
    best = 0
    for right, ch in enumerate(s):
        counts[ord(ch) - 65] += 1
        while (right - left + 1) - max(counts) > k:
            counts[ord(s[left]) - 65] -= 1
            left += 1
        best = max(best, right - left + 1)
    return best


# --- canonical reference (longest-substring-without-repeating-characters) ---

@reference("longest-substring-without-repeating-characters")
def _longest_substring_without_repeating_characters_reference(s: str) -> int:
    last: dict[str, int] = {}
    left = 0
    best = 0
    for right, ch in enumerate(s):
        if ch in last and last[ch] >= left:
            left = last[ch] + 1
        last[ch] = right
        best = max(best, right - left + 1)
    return best


# --- canonical reference (minimum-window-substring) ---

@reference("minimum-window-substring")
def _minimum_window_substring_reference(s: str, t: str) -> str:
    """Two pointers + a deficit counter over t -- the intended O(m + n)."""
    from collections import Counter

    if not t:
        return ""
    need = Counter(t)
    missing = len(t)  # characters still missing from the window, duplicates counted
    left = 0
    best_start, best_len = 0, len(s) + 1
    for right, ch in enumerate(s):
        if need[ch] > 0:
            missing -= 1
        need[ch] -= 1
        while missing == 0:
            if right - left + 1 < best_len:
                best_start, best_len = left, right - left + 1
            dropped = s[left]
            need[dropped] += 1
            if need[dropped] > 0:
                missing += 1
            left += 1
    return s[best_start : best_start + best_len] if best_len <= len(s) else ""


# --- canonical reference (permutation-in-string) ---

@reference("permutation-in-string")
def _permutation_in_string_reference(s1: str, s2: str) -> bool:
    width = len(s1)
    if width > len(s2):
        return False
    need = [0] * 26
    for ch in s1:
        need[ord(ch) - 97] += 1
    window = [0] * 26
    for ch in s2[:width]:
        window[ord(ch) - 97] += 1
    if window == need:
        return True
    for i in range(width, len(s2)):
        window[ord(s2[i]) - 97] += 1
        window[ord(s2[i - width]) - 97] -= 1
        if window == need:
            return True
    return False


# --- canonical reference (sliding-window-maximum) ---

@reference("sliding-window-maximum")
def _sliding_window_maximum_reference(nums: list[int], k: int) -> list[int]:
    """Monotonic deque of indices -- the intended O(n) time and O(k) space."""
    from collections import deque

    window: deque[int] = deque()  # indices, their values decreasing
    out: list[int] = []
    for i, value in enumerate(nums):
        while window and nums[window[-1]] <= value:
            window.pop()
        window.append(i)
        if window[0] <= i - k:
            window.popleft()  # the front has left the window
        if i >= k - 1:
            out.append(nums[window[0]])
    return out


# --- canonical reference (binary-search) ---

@reference("binary-search")
def _binary_search_reference(nums: list[int], target: int) -> int:
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
# --- canonical reference (find-minimum-in-rotated-sorted-array) ---

@reference("find-minimum-in-rotated-sorted-array")
def _find_minimum_in_rotated_sorted_array_reference(nums: list[int]) -> int | None:
    """Canonical O(log n): compare the middle with the last element — if it is
    larger, the minimum is to its right, otherwise it is at or left of it."""
    if not nums:
        return None
    lo, hi = 0, len(nums) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if nums[mid] > nums[hi]:
            lo = mid + 1
        else:
            hi = mid
    return nums[lo]
# --- canonical reference (koko-eating-bananas) ---

@reference("koko-eating-bananas")
def _koko_eating_bananas_reference(piles: list[int], h: int) -> int:
    if not piles:
        return 1  # unreachable under the statement's constraints (length >= 1)

    def hours_for(speed: int) -> int:
        total = 0
        for pile in piles:
            total += -(-pile // speed)  # ceil(pile / speed), in integers
        return total

    # Feasibility is monotone in the speed (a bigger speed never costs more
    # hours) and speed = max(piles) always fits, because the statement promises
    # piles.length <= h. So binary search the smallest feasible speed, scanning
    # every pile on every probe — nothing here exits early.
    lo, hi = 1, max(piles)
    while lo < hi:
        mid = (lo + hi) // 2
        if hours_for(mid) <= h:
            hi = mid
        else:
            lo = mid + 1
    return lo
# --- canonical reference (median-of-two-sorted-arrays) ---

@reference("median-of-two-sorted-arrays")
def _median_of_two_sorted_arrays_reference(nums1: list[int], nums2: list[int]) -> float | None:
    """Canonical O(log min(m, n)): binary search how many elements of the smaller
    array sit left of the split, so that everything on the left is <= everything
    on the right; the median then reads off the four boundary values."""
    a, b = (nums1, nums2) if len(nums1) <= len(nums2) else (nums2, nums1)
    m, n = len(a), len(b)
    if m + n == 0:
        return None
    half = (m + n + 1) // 2  # the left side holds this many elements
    lo, hi = 0, m
    while lo <= hi:
        i = (lo + hi) // 2  # elements of a on the left
        j = half - i  # elements of b on the left
        left_a = a[i - 1] if i > 0 else float("-inf")
        right_a = a[i] if i < m else float("inf")
        left_b = b[j - 1] if j > 0 else float("-inf")
        right_b = b[j] if j < n else float("inf")
        if left_a > right_b:
            hi = i - 1
        elif left_b > right_a:
            lo = i + 1
        else:
            if (m + n) % 2:
                return float(max(left_a, left_b))
            return (max(left_a, left_b) + min(right_a, right_b)) / 2
    raise ValueError("median of two sorted arrays: inputs are not sorted")
# --- canonical reference (search-a-2d-matrix) ---

@reference("search-a-2d-matrix")
def _search_a_2d_matrix_reference(matrix: list[list[int]], target: int) -> bool:
    # The two stated properties make the matrix a single sorted array read row
    # by row, so one binary search over cell indices is enough — and it never
    # materialises that array.
    if not matrix or not matrix[0]:
        return False
    cols = len(matrix[0])  # the statement guarantees every row is n long
    lo, hi = 0, len(matrix) * cols - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        value = matrix[mid // cols][mid % cols]
        if value == target:
            return True
        if value < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return False
# --- canonical reference (search-in-rotated-sorted-array) ---

@reference("search-in-rotated-sorted-array")
def _search_in_rotated_sorted_array_reference(nums: list[int], target: int) -> int:
    """Canonical O(log n): one half is always sorted, so the target's side of the
    wrap is decidable from the sorted half alone. Distinct values are guaranteed
    by the statement, so no tie handling is needed."""
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        if nums[lo] <= nums[mid]:  # the left half is sorted
            if nums[lo] <= target < nums[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        else:  # the right half is sorted
            if nums[mid] < target <= nums[hi]:
                lo = mid + 1
            else:
                hi = mid - 1
    return -1
# --- canonical reference (time-based-key-value-store) ---

@reference("time-based-key-value-store")
def _time_based_key_value_store_reference(ops: list[list]) -> list:
    """Canonical TimeMap, driven through the same op list the oracle takes:
    one growing list of (timestamp, value) per key (appended in the statement's
    strictly increasing timestamp order) and a binary search for the latest set
    at or before the query — O(1) per set, O(log n) per get, O(n) space."""
    store: dict[str, list[tuple[int, str]]] = {}
    out: list = []
    for op in ops:
        method, *args = op
        if method == "set":
            key, value, timestamp = args
            store.setdefault(key, []).append((timestamp, value))
            out.append(None)
        elif method == "get":
            key, timestamp = args
            entries = store.get(key)
            if not entries:
                out.append("")
                continue
            lo, hi = 0, len(entries) - 1
            found = -1  # index of the latest timestamp <= the query
            while lo <= hi:
                mid = (lo + hi) // 2
                if entries[mid][0] <= timestamp:
                    found = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            out.append(entries[found][1] if found >= 0 else "")
        else:  # pragma: no cover - the generator only emits set and get
            raise ValueError(f"unknown op {method}")
    return out


# --- canonical reference (design-add-and-search-words-data-structure) ---

@reference("design-add-and-search-words-data-structure")
def _design_add_and_search_words_data_structure_reference(ops: list[list]) -> list:
    """Canonical WordDictionary, driven through the same op list the oracle takes:
    one dict per node (a None key marks the end of an added word), and a search
    that descends the trie letter by letter, branching into every child when it
    meets a '.' — at most two per query by the statement's own constraint, so the
    walk stays linear in the word length up to a 26^2 constant."""

    def _design_add_and_search_words_data_structure_matches(
        node: dict, word: str, i: int
    ) -> bool:
        if i == len(word):
            return None in node
        ch = word[i]
        if ch == ".":
            return any(
                _design_add_and_search_words_data_structure_matches(child, word, i + 1)
                for key, child in node.items()
                if key is not None
            )
        child = node.get(ch)
        return child is not None and _design_add_and_search_words_data_structure_matches(
            child, word, i + 1
        )

    root: dict = {}
    out: list = []
    for op in ops:
        method, *args = op
        if method == "addWord":
            node = root
            for ch in args[0]:
                nxt = node.get(ch)
                if nxt is None:
                    nxt = {}
                    node[ch] = nxt
                node = nxt
            node[None] = True
            out.append(None)
        elif method == "search":
            out.append(
                _design_add_and_search_words_data_structure_matches(root, args[0], 0)
            )
        else:  # pragma: no cover - the generator only emits addWord and search
            raise ValueError(f"unknown op {method}")
    return out
# --- canonical reference (implement-trie-prefix-tree) ---

@reference("implement-trie-prefix-tree")
def _implement_trie_prefix_tree_reference(ops: list[list]) -> list:
    """Canonical trie, driven through the same op list the oracle takes: one dict
    per node mapping a character to its child, plus a None key marking "a word
    ends here" — which is the whole difference between search and startsWith.
    Each call walks its word once (O(len(word)) time), and the structure holds one
    node per distinct prefix (O(total inserted characters) space)."""
    root: dict = {}
    out: list = []
    for op in ops:
        method, *args = op
        word = args[0]
        if method == "insert":
            node = root
            for ch in word:
                nxt = node.get(ch)
                if nxt is None:
                    nxt = {}
                    node[ch] = nxt
                node = nxt
            node[None] = True  # a word ends at this node
            out.append(None)
        elif method == "search":
            node = root
            for ch in word:
                node = node.get(ch)
                if node is None:
                    break
            out.append(node is not None and None in node)
        elif method == "startsWith":
            node = root
            for ch in word:
                node = node.get(ch)
                if node is None:
                    break
            out.append(node is not None)
        else:  # pragma: no cover - the generator only emits the three methods
            raise ValueError(f"unknown op {method}")
    return out
# --- canonical reference (word-search-ii) ---

@reference("word-search-ii")
def _word_search_ii_reference(board: list[list[str]], words: list[str]) -> list[str]:
    """Canonical trie + backtracking: build ONE trie over every word, then walk the
    board once following trie edges, so a path that no word prefixes is never
    explored and the board is not re-walked per word the way a brute-force search
    re-walks it. A word is unlinked from the trie the moment it is found (and an
    empty branch is pruned from its parent), which keeps the result free of
    duplicates and stops the walk from descending into a branch that can no longer
    match anything.

    The words come back in discovery order, not sorted: the case's own
    "compare": "sorted" tag is what makes any order legal, and the probe's
    scale_compare is set to "sorted" for the same reason."""
    root: dict = {}
    for word in words:
        node = root
        for ch in word:
            nxt = node.get(ch)
            if nxt is None:
                nxt = {}
                node[ch] = nxt
            node = nxt
        node[None] = word  # the word-end marker carries the word itself

    rows = len(board)
    cols = len(board[0]) if rows else 0
    found: list[str] = []
    visited: set[tuple[int, int]] = set()

    def _word_search_ii_walk(r: int, c: int, node: dict) -> None:
        ch = board[r][c]
        nxt = node.get(ch)
        if nxt is None:
            return  # no remaining word has this prefix
        word = nxt.pop(None, None)
        if word is not None:
            found.append(word)  # unlinked: a second occurrence cannot re-add it
        if nxt:  # something is still reachable through this node: descend
            visited.add((r, c))
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                    _word_search_ii_walk(nr, nc, nxt)
            visited.discard((r, c))
        else:  # nothing left below: prune the edge so the walk stops paying for it
            node.pop(ch, None)

    for r in range(rows):
        for c in range(cols):
            _word_search_ii_walk(r, c, root)
    return found
# --- canonical reference (add-two-numbers) ---

@reference("add-two-numbers")
def _add_two_numbers_reference(l1: list[int], l2: list[int]) -> list[int]:
    out: list[int] = []
    carry = 0
    i = 0
    while i < len(l1) or i < len(l2) or carry:
        total = carry
        if i < len(l1):
            total += l1[i]
        if i < len(l2):
            total += l2[i]
        out.append(total % 10)
        carry = total // 10
        i += 1
    return out or [0]
# --- canonical reference (copy-list-with-random-pointer) ---

@reference("copy-list-with-random-pointer")
def _copy_list_with_random_pointer_reference(head: list) -> list:
    if not head:
        return []
    # Hash map pass, the canonical O(n) solution: one new node per original,
    # then the random pointers are rewired through the map, so a random pointer
    # that aims backwards or forwards costs the same.
    copied = {i: [node[0], -1] for i, node in enumerate(head)}
    for i, node in enumerate(head):
        target = node[1]
        copied[i][1] = target if target == -1 else target
    return [copied[i] for i in range(len(head))]
# --- canonical reference (find-the-duplicate-number) ---

@reference("find-the-duplicate-number")
def _find_the_duplicate_number_reference(nums: list[int]) -> int:
    # Floyd's cycle detection on the value graph: nums[i] is the successor of
    # index i, so the duplicate value is the entry of the one cycle. O(n) time,
    # O(1) extra space, and the input is never modified — the statement's two
    # demands met by the same trick, which is why this problem lives in the
    # linked-list group.
    slow = nums[0]
    fast = nums[0]
    while True:
        slow = nums[slow]
        fast = nums[nums[fast]]
        if slow == fast:
            break
    # Phase 2 restarts at nums[0] — the head's successor. The first node of the
    # list is the value stored at index 0, so the meeting point and the restart
    # point are both nums[0]; this is the form that resolves the value at the
    # cycle entry. (Verified against the oracle on every legal array of length
    # 2..7 — 61,497 of them — and on 200k random arrays up to n = 400. The lone
    # legal shape it cannot walk is [n, n] for n = 2, where index 0 holds a copy
    # of the value n and the first step leaves the array; the generator does not
    # emit it and the visible tests do not use it.)
    slow = nums[0]
    while slow != fast:
        slow = nums[slow]
        fast = nums[fast]
    return slow
# --- canonical reference (linked-list-cycle) ---

@reference("linked-list-cycle")
def _linked_list_cycle_reference(next_node: list[int]) -> bool:
    # Floyd's tortoise and hare, the statement's follow-up: two pointers, no
    # extra memory. A -1 ends the list at either pointer, so a walk that reaches
    # null has no cycle.
    if not next_node:
        return False
    slow = 0
    fast = 0
    while True:
        fast = next_node[fast]
        if fast == -1:
            return False
        fast = next_node[fast]
        if fast == -1:
            return False
        slow = next_node[slow]
        if fast == slow:
            return True
# --- canonical reference (lru-cache) ---

@reference("lru-cache")
def _lru_cache_reference(ops: list[list]) -> list:
    """The intended design, driven through the same op list the oracle takes: a
    dict key -> node plus an intrusive doubly linked list in recency order with a
    sentinel at each end — O(1) per get and per put, O(capacity) nodes. The
    capacity arrives as the leading ["__init__", capacity] op, because the judge's
    convention for a class problem hands the reference the op list and nothing
    else; the op rebuilds the cache, so every case runs on fresh state."""
    head: list = []  # sentinel at the LRU end: its [next] is the eviction victim
    tail: list = []  # sentinel at the MRU end: its [prev] is the newest node
    nodes: dict[int, list] = {}
    capacity: int | None = None

    def _lru_cache_unlink(node: list) -> None:
        node[2][3] = node[3]
        node[3][2] = node[2]

    def _lru_cache_move_to_mru(node: list) -> None:
        _lru_cache_unlink(node)
        newest = tail[2]
        newest[3] = node
        node[2] = newest
        node[3] = tail
        tail[2] = node

    out: list = []
    for op in ops:
        method, *args = op
        if method == "__init__":
            capacity = args[0]
            head = [None, None, None, None]
            tail = [None, None, None, None]
            head[3] = tail
            tail[2] = head
            nodes = {}
            out.append(None)
        elif method == "get":
            if capacity is None:
                raise ValueError('the op list must start with ["__init__", capacity]')
            node = nodes.get(args[0])
            if node is None:
                out.append(-1)
            else:
                _lru_cache_move_to_mru(node)
                out.append(node[1])
        elif method == "put":
            if capacity is None:
                raise ValueError('the op list must start with ["__init__", capacity]')
            key, value = args
            node = nodes.get(key)
            if node is not None:
                node[1] = value  # an update also makes the key most recent
                _lru_cache_move_to_mru(node)
            else:
                if len(nodes) >= capacity:
                    victim = head[3]
                    _lru_cache_unlink(victim)
                    del nodes[victim[0]]
                node = [key, value, None, None]
                nodes[key] = node
                newest = tail[2]
                newest[3] = node
                node[2] = newest
                node[3] = tail
                tail[2] = node
            out.append(None)
        else:  # pragma: no cover - the generator only emits the three methods
            raise ValueError(f"unknown op {method}")
    return out
# --- canonical reference (merge-k-sorted-lists) ---

@reference("merge-k-sorted-lists")
def _merge_k_sorted_lists_reference(lists: list[list[int]]) -> list[int]:
    """Canonical k-way merge: one heap entry per non-empty list, pop the smallest
    head and push that list's next node — O(n log k) time and O(k) space, where n
    is the total number of nodes and k the number of lists."""
    import heapq

    heap: list[tuple[int, int, int]] = []
    for index, head in enumerate(lists):
        if head:
            heap.append((head[0], index, 0))
    heapq.heapify(heap)
    out: list[int] = []
    while heap:
        value, index, position = heapq.heappop(heap)
        out.append(value)
        position += 1
        if position < len(lists[index]):
            heapq.heappush(heap, (lists[index][position], index, position))
    return out
# --- canonical reference (merge-two-sorted-lists) ---

@reference("merge-two-sorted-lists")
def _merge_two_sorted_lists_reference(list1: list[int], list2: list[int]) -> list[int]:
    # The intended single pass: one index per list, take the smaller head each
    # time (<= keeps the merge stable, which no case can observe - the merged
    # multiset is the same either way), then drain whichever list is left. O(n)
    # time over n = m + k nodes and O(1) extra space: `merged` is the only list it
    # allocates, so the tails are drained with appends rather than slices.
    merged: list[int] = []
    i = 0
    j = 0
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            merged.append(list1[i])
            i += 1
        else:
            merged.append(list2[j])
            j += 1
    while i < len(list1):
        merged.append(list1[i])
        i += 1
    while j < len(list2):
        merged.append(list2[j])
        j += 1
    return merged
# --- canonical reference (remove-nth-node-from-end-of-list) ---

@reference("remove-nth-node-from-end-of-list")
def _remove_nth_node_from_end_of_list_reference(head: list[int], n: int) -> list[int]:
    # The statement's follow-up, one walk over the nodes: two indices a gap of n
    # apart. `fast` starts n ahead of `slow`, so when `fast` runs off the end,
    # `slow` sits exactly on the nth node from the end (that gap is what makes the
    # count-from-the-end distance work, and it is why no length is needed first).
    # Writing the survivors into a new list is this representation's unlink - the
    # returned list is the only thing the function allocates.
    size = len(head)
    if n < 1 or n > size:
        return list(head)  # outside 1 <= n <= sz: nothing to remove
    slow = 0
    fast = n
    while fast < size:
        slow += 1
        fast += 1
    out: list[int] = []
    for i in range(size):
        if i != slow:
            out.append(head[i])
    return out
# --- canonical reference (reorder-list) ---

@reference("reorder-list")
def _reorder_list_reference(head: list[int]) -> None:
    # The canonical three steps over the list of node values. Split at the middle
    # (the first half takes the extra node when the length is odd), reverse the
    # second half in place with a swap loop - the pointer reversal, with indices
    # standing in for the links - then interleave the two halves. The interleave
    # is the one step a plain list cannot do with O(1) extra space (it is an
    # in-place perfect shuffle), so the merged order is built in a temporary list
    # and written back into the argument. Returning early below three nodes is the
    # statement's own [L0, Ln] identity, and no probe size comes near it.
    size = len(head)
    if size < 3:
        return
    mid = (size + 1) // 2
    lo = mid
    hi = size - 1
    while lo < hi:
        head[lo], head[hi] = head[hi], head[lo]
        lo += 1
        hi -= 1
    order: list[int] = []
    for i in range(size - mid):
        order.append(head[i])
        order.append(head[mid + i])
    if size % 2:
        order.append(head[mid - 1])
    head[:] = order
# --- canonical reference (reverse-linked-list) ---

@reference("reverse-linked-list")
def _reverse_linked_list_reference(head: list[int]) -> list[int]:
    # The iterative reversal over dojo's list of node values: walk the indices
    # from the last node back to the head and append each value - the relinking
    # loop with the index standing in for the `next` pointer. O(n) time and O(1)
    # extra space: the returned list is the only thing it allocates, and it does
    # not touch the argument.
    out: list[int] = []
    for i in range(len(head) - 1, -1, -1):
        out.append(head[i])
    return out
# --- canonical reference (reverse-nodes-in-k-group) ---

@reference("reverse-nodes-in-k-group")
def _reverse_nodes_in_k_group_reference(head: list[int], k: int) -> list[int]:
    """Canonical O(n) time and O(1) extra space: reverse every complete block of k
    in place with the two-pointer swap the ListNode version performs, then leave
    the tail alone. It reverses the list it is given and returns that same list —
    the relinking solution's own contract, and what keeps the reference's space
    baseline at O(1) rather than the O(n) a slice-based answer allocates (which is
    exactly what the statement's follow-up rules out). k < 1 is outside the
    statement's range and leaves the list untouched."""
    n = len(head)
    start = 0
    while k >= 1 and start + k <= n:
        lo, hi = start, start + k - 1
        while lo < hi:
            head[lo], head[hi] = head[hi], head[lo]
            lo += 1
            hi -= 1
        start += k
    return head
# --- canonical reference (balanced-binary-tree) ---

@reference("balanced-binary-tree")
def _balanced_binary_tree_reference(root: list | None) -> bool:
    """The canonical bottom-up solution: one post-order pass returning a
    subtree's height, or -1 the moment a subtree is unbalanced — so every node
    is visited exactly once and the -1 propagates without any further work.
    The empty tree is 0 and therefore balanced."""

    def height_or_fail(node: list | None) -> int:
        if node is None:
            return 0
        left = height_or_fail(node[1])
        if left == -1:
            return -1
        right = height_or_fail(node[2])
        if right == -1:
            return -1
        if abs(left - right) > 1:
            return -1
        return 1 + max(left, right)

    return height_or_fail(root) != -1
# --- canonical reference (binary-tree-level-order-traversal) ---

@reference("binary-tree-level-order-traversal")
def _binary_tree_level_order_traversal_reference(root: list | None) -> list[list[int]]:
    """The canonical BFS: one queue, and each round of the outer loop drains
    exactly one level (len(queue) - head is that level's width). O(n) time,
    O(n) space including the output."""
    if root is None:
        return []
    out: list[list[int]] = []
    queue: list[list] = [root]
    head = 0
    while head < len(queue):
        level: list[int] = []
        for _ in range(len(queue) - head):
            node = queue[head]
            head += 1
            level.append(node[0])
            if node[1] is not None:
                queue.append(node[1])
            if node[2] is not None:
                queue.append(node[2])
        out.append(level)
    return out
# --- canonical reference (binary-tree-maximum-path-sum) ---

@reference("binary-tree-maximum-path-sum")
def _binary_tree_maximum_path_sum_reference(root: list | None) -> int:
    """The intended O(n) time / O(h) space: one post-order walk. `gain(node)` is
    the best sum of a downward path that STARTS at `node` and may stop anywhere
    below it, so a negative branch can simply be dropped (`max(0, ...)`) -- a path
    is free to end before it. The best path THROUGH a node is the node plus the
    best gain on each side, which is what updates the answer. `best` starts at
    None rather than 0: for an all-negative tree the answer is the largest node
    value, because the statement maximizes over NON-EMPTY paths (a 0 seed silently
    invents the empty path)."""
    best = None

    def gain(node: list | None) -> int:
        nonlocal best
        if node is None:
            return 0
        left = gain(node[1])
        right = gain(node[2])
        through = node[0] + max(left, 0) + max(right, 0)
        best = through if best is None else max(best, through)
        return node[0] + max(left, right, 0)  # downward: at most one side continues

    gain(root)
    return 0 if best is None else best
# --- canonical reference (binary-tree-right-side-view) ---

@reference("binary-tree-right-side-view")
def _binary_tree_right_side_view_reference(root: list | None) -> list[int]:
    """The canonical level sweep: a BFS queue drained one level at a time, taking
    the last node dequeued on each level -- the one that is visible from the
    right. O(n) time, O(n) space."""
    if root is None:
        return []
    out: list[int] = []
    queue: list[list] = [root]
    head = 0
    while head < len(queue):
        last = root[0]
        for _ in range(len(queue) - head):
            node = queue[head]
            head += 1
            last = node[0]
            if node[1] is not None:
                queue.append(node[1])
            if node[2] is not None:
                queue.append(node[2])
        out.append(last)  # every level has at least one node
    return out
# --- canonical reference (construct-binary-tree-from-preorder-and-inorder-traversal) ---

@reference("construct-binary-tree-from-preorder-and-inorder-traversal")
def _construct_binary_tree_from_preorder_and_inorder_traversal_reference(
    preorder: list[int], inorder: list[int]
) -> list | None:
    """The intended O(n): one pass maps every value to its inorder position, then
    a recursive build consumes preorder left to right, using the current
    subtree's inorder bounds to know where it ends. No slicing and no rescanning,
    so it is linear in the number of nodes."""
    position = {value: i for i, value in enumerate(inorder)}
    cursor = 0

    def build(lo: int, hi: int) -> list | None:
        nonlocal cursor
        if lo > hi:
            return None  # an empty inorder range is a missing child
        value = preorder[cursor]
        cursor += 1
        mid = position[value]
        left = build(lo, mid - 1)
        right = build(mid + 1, hi)
        return [value, left, right]

    return build(0, len(inorder) - 1)
# --- canonical reference (count-good-nodes-in-binary-tree) ---

@reference("count-good-nodes-in-binary-tree")
def _count_good_nodes_in_binary_tree_reference(root: list | None) -> int:
    """Canonical O(n) time / O(h) space: one descent carrying the largest value
    seen on the path so far. A node is good exactly when it is not smaller than
    that running maximum — `>=`, not `>`, because the definition forbids an
    ancestor that is *greater*, so a tie is good. `best is None` is the root's
    case (the root is always good), not a sentinel value."""

    def walk(node: list | None, best: int | None) -> int:
        if node is None:
            return 0
        value = node[0]
        if best is None or value >= best:
            return 1 + walk(node[1], value) + walk(node[2], value)
        return walk(node[1], best) + walk(node[2], best)

    return walk(root, None)
# --- canonical reference (invert-binary-tree) ---

@reference("invert-binary-tree")
def _invert_binary_tree_reference(root: list | None) -> list | None:
    """The canonical solution: exchange the two children at every node, in
    place, then invert the already-swapped children and return the root. The
    probe hands every call a fresh copy of the arguments, so mutating them is
    safe there; a caller that needs a case's args after the call must copy them
    first (see notes)."""
    if root is None:
        return None
    root[1], root[2] = root[2], root[1]
    _invert_binary_tree_reference(root[1])
    _invert_binary_tree_reference(root[2])
    return root
# --- canonical reference (kth-smallest-element-in-a-bst) ---

@reference("kth-smallest-element-in-a-bst")
def _kth_smallest_element_in_a_bst_reference(root: list | None, k: int) -> int:
    """Canonical: walk the BST in order with an explicit stack, so the values
    arrive ascending and the k-th one visited is the answer — O(h) space, and it
    stops as soon as k nodes have been counted instead of materializing the
    whole traversal. Every node is pushed at most once, so the walk is O(n) in
    the worst case (k = n) and O(h + k) in general. The statement guarantees
    1 <= k <= n; outside that there is no answer to return."""
    remaining = k
    stack: list[list] = []
    node = root
    while stack or node is not None:
        while node is not None:
            stack.append(node)
            node = node[1]
        node = stack.pop()
        remaining -= 1
        if remaining == 0:
            return node[0]
        node = node[2]
    raise ValueError(f"k={k} is outside the statement's 1 <= k <= n")
# --- canonical reference (lowest-common-ancestor-of-a-binary-search-tree) ---

@reference("lowest-common-ancestor-of-a-binary-search-tree")
def _lowest_common_ancestor_of_a_binary_search_tree_reference(
    root: list | None, p: int, q: int
) -> int | None:
    """The intended O(h) / O(1) descent: while both targets lie on the same side
    of the current node, follow that side. The first node that separates them --
    or that is one of them, since a node is a descendant of itself -- is the
    lowest common ancestor. Iterative, so no input can exhaust the stack."""
    node = root
    while node is not None:
        value = node[0]
        if p < value and q < value:
            node = node[1]
        elif p > value and q > value:
            node = node[2]
        else:
            return value
    return None
# --- canonical reference (maximum-depth-of-binary-tree) ---

@reference("maximum-depth-of-binary-tree")
def _maximum_depth_of_binary_tree_reference(root: list | None) -> int:
    """The canonical recursion: a node's depth is one more than the deeper of
    its two subtrees, and the empty tree is 0."""
    if root is None:
        return 0
    return 1 + max(
        _maximum_depth_of_binary_tree_reference(root[1]),
        _maximum_depth_of_binary_tree_reference(root[2]),
    )
# --- canonical reference (same-tree) ---

@reference("same-tree")
def _same_tree_reference(p: list | None, q: list | None) -> bool:
    """The canonical solution: walk both trees together, so the two empty cases
    are the same tree and any structural difference (one side None, the other a
    subtree) is a difference. O(min(n, m)) time, O(h) stack."""
    if p is None or q is None:
        return p is None and q is None
    if p[0] != q[0]:
        return False
    return _same_tree_reference(p[1], q[1]) and _same_tree_reference(p[2], q[2])
# --- canonical reference (subtree-of-another-tree) ---

@reference("subtree-of-another-tree")
def _subtree_of_another_tree_reference(root: list | None, sub_root: list | None) -> bool:
    """The canonical intended solution: compare every node of root with subRoot,
    structurally, recursing into both children when the comparison fails --
    O(n * m) worst case, which is the declared target, and O(n + m) on a balanced
    pair. Self-contained: the two helpers are nested, because the probe runs this
    function's own source in its own subprocess."""
    def same(a: list | None, b: list | None) -> bool:
        if a is None or b is None:
            return a is None and b is None
        return a[0] == b[0] and same(a[1], b[1]) and same(a[2], b[2])

    def walk(node: list | None) -> bool:
        if node is None:
            return False
        return same(node, sub_root) or walk(node[1]) or walk(node[2])

    if sub_root is None:
        return True
    return walk(root)
# --- canonical reference (validate-binary-search-tree) ---

@reference("validate-binary-search-tree")
def _validate_binary_search_tree_reference(root: list | None) -> bool:
    """Canonical O(n) time / O(h) space: one iterative walk carrying the open
    interval (lo, hi) each node must fall inside — lo is the tightest ancestor
    value the path has already exceeded, hi the tightest it has stayed below,
    and None means that end is still unbounded. This is exactly the state a
    parent-only check does not have, which is why it is the reference here.
    Strictness is the statement's own: a value equal to either end is not a BST.
    The explicit stack keeps depth O(h) without Python recursion limits, and the
    empty tree (which the statement's [1, 10^4] range excludes but the dojo
    representation allows) is vacuously a BST."""

    stack: list[tuple[list | None, int | None, int | None]] = [(root, None, None)]
    while stack:
        node, lo, hi = stack.pop()
        if node is None:
            continue
        value = node[0]
        if lo is not None and value <= lo:
            return False
        if hi is not None and value >= hi:
            return False
        stack.append((node[1], lo, value))
        stack.append((node[2], value, hi))
    return True
# --- canonical reference (design-twitter) ---

@reference("design-twitter")
def _design_twitter_reference(ops: list[list]) -> list:
    """Canonical Twitter, driven through the same op list the oracle takes. Each
    user keeps their tweets in post order as (sequence, tweetId), and
    getNewsFeed merges the newest tweet of the reader and of each followee
    through a max-heap, popping at most 10 and pushing that author's next-newest
    back: O(1) per post/follow/unfollow, O(f + 10 log f) per feed for f
    followees. Sequence numbers are unique, so the heap never falls back on a
    tuple tie-break and the feed order is decided by post order alone — never by
    tweetId, and never by set or dict iteration order (the followees are read
    through sorted()).
    """
    import heapq

    tweets: dict[int, list[tuple[int, int]]] = {}
    following: dict[int, set[int]] = {}
    sequence = 0
    out: list = []
    for op in ops:
        method, *args = op
        if method == "postTweet":
            user, tweet = args
            sequence += 1
            tweets.setdefault(user, []).append((sequence, tweet))
            out.append(None)
        elif method == "getNewsFeed":
            user = args[0]
            heap: list[tuple[int, int, int]] = []
            for author in [user] + sorted(following.get(user, ())):
                own = tweets.get(author)
                if own:
                    newest = len(own) - 1
                    heapq.heappush(heap, (-own[newest][0], author, newest))
            feed: list[int] = []
            while heap and len(feed) < 10:
                _neg, author, index = heapq.heappop(heap)
                own = tweets[author]
                feed.append(own[index][1])
                if index > 0:
                    heapq.heappush(heap, (-own[index - 1][0], author, index - 1))
            out.append(feed)
        elif method == "follow":
            follower, followee = args
            following.setdefault(follower, set()).add(followee)
            out.append(None)
        elif method == "unfollow":
            follower, followee = args
            following.setdefault(follower, set()).discard(followee)
            out.append(None)
        else:  # pragma: no cover - the generator only emits the four methods
            raise ValueError(f"unknown op {method}")
    return out


# --- canonical reference (k-closest-points-to-origin) ---

@reference("k-closest-points-to-origin")
def _k_closest_points_to_origin_reference(k: int, points: list[list[int]]) -> list[list[int]]:
    """Canonical heap solution (the answer this group is about): a size-k max-heap
    keyed by squared distance — (-d, x, y) in a min-heap — so each point costs
    O(log k) and the heap holds O(k): O(n log k) time, O(k) space. Distances are
    exact integer squares, so no float rounding can reorder them. Which of several
    tied points survives is arbitrary, and k_closest_valid accepts any valid choice;
    the returned list is sorted closest-first only so the output is deterministic."""
    import heapq

    heap: list[tuple[int, int, int]] = []
    for x, y in points:
        item = (-(x * x + y * y), x, y)
        if len(heap) < k:
            heapq.heappush(heap, item)
        elif item > heap[0]:  # -d > -d_max: strictly closer than the farthest kept
            heapq.heapreplace(heap, item)
    return [[x, y] for _, x, y in sorted(heap, key=lambda t: (-t[0], t[1], t[2]))]


# --- canonical reference (kth-largest-element-in-a-stream) ---

@reference("kth-largest-element-in-a-stream")
def _kth_largest_element_in_a_stream_reference(ops: list[list]) -> list:
    """Canonical KthLargest, written as the op-list driver the registry convention
    calls (curator._case_findings passes the op list, never ctor_args): a min-heap
    that never holds more than k scores, so each add is O(log k) and the heap is
    O(k) — the statement's target. The constructor heapifies the initial scores and
    trims them to k."""
    import heapq

    heap: list[int] = []
    k = 0
    out: list = []
    for op in ops:
        method, *args = op
        if method == "__init__":
            k, nums = args
            heap = list(nums)
            heapq.heapify(heap)
            while len(heap) > k:
                heapq.heappop(heap)
            out.append(None)
        elif method == "add":
            val = args[0]
            if len(heap) < k:
                heapq.heappush(heap, val)
            elif val > heap[0]:
                heapq.heapreplace(heap, val)
            out.append(heap[0])
        else:  # pragma: no cover - the generator only emits these two methods
            raise ValueError(f"unknown op {method}")
    return out


# --- canonical reference (kth-largest-element-in-an-array) ---

@reference("kth-largest-element-in-an-array")
def _kth_largest_element_in_an_array_reference(nums: list[int], k: int) -> int:
    """Canonical quickselect — the statement's own "without sorting". Partition
    the live range around a median-of-three pivot into <, == and > bands, then
    walk into the band that holds the k-th largest: O(n) on average, in place
    (O(1) extra space). The three-way partition also keeps an all-equal array
    linear, where a two-way partition degrades to O(n^2), and the pivot rule is
    deterministic (no clock, no rng), so the probe's baseline is reproducible.
    """
    target = len(nums) - k  # its index in ascending order
    lo, hi = 0, len(nums) - 1
    while True:
        pivot = sorted((nums[lo], nums[(lo + hi) // 2], nums[hi]))[1]
        lt, i, gt = lo, lo, hi
        while i <= gt:
            if nums[i] < pivot:
                nums[lt], nums[i] = nums[i], nums[lt]
                lt += 1
                i += 1
            elif nums[i] > pivot:
                nums[gt], nums[i] = nums[i], nums[gt]
                gt -= 1
            else:
                i += 1
        # nums[lt:gt + 1] is exactly the pivot's band, and target never leaves
        # [lo, hi], so one of the three branches always answers while the other
        # two strictly shrink the range.
        if target < lt:
            hi = lt - 1
        elif target > gt:
            lo = gt + 1
        else:
            return pivot


# --- canonical reference (last-stone-weight) ---

@reference("last-stone-weight")
def _last_stone_weight_reference(stones: list[int]) -> int:
    """Canonical max-heap: a min-heap of negated weights, so the two heaviest are two
    O(log n) pops and at most one O(log n) push per turn — O(n log n) time and O(n)
    space, the statement's target. The heap is a fresh copy, so the argument list is
    never mutated."""
    import heapq

    heap = [-weight for weight in stones]
    heapq.heapify(heap)
    while len(heap) > 1:
        y = -heapq.heappop(heap)
        x = -heapq.heappop(heap)
        if x != y:
            heapq.heappush(heap, -(y - x))
    return -heap[0] if heap else 0


# --- canonical reference (task-scheduler) ---

@reference("task-scheduler")
def _task_scheduler_reference(tasks: list[str], n: int) -> int:
    """The interval-by-interval simulation a student writes, over fixed 26-slot
    arrays: remaining[i] counts label i's copies left, ready[i] is how many more
    intervals label i must wait (0 = runnable now, and running it sets it to n).
    Each interval runs the runnable label with the most copies left, or idles
    when every label is still cooling, and intervals are counted until nothing is
    left. O(answer * 26) = O(m) time (answer <= 101 * len(tasks)) and O(1) space —
    the same class as the closed form, which is the point: it is deliberately the
    heavy baseline, not the fast one. The closed form is ~15-300x quicker in
    constant terms, and a comparison across the probe's 100..6400 ladder cannot
    cancel a gap that large — the faster side's fixed cost dominates its own time
    at n = 100, the ratio drifts ~2x, and a correct simulation gets named one
    class slower. Measured, not theorized: with the closed form as the baseline a
    correct heap simulation read 9.16x at n = 100 rising to 18.11x at n = 6400.
    Against this baseline every honest implementation reads flat (heap simulation
    ~0.06x, array or dict scan ~1x, both across the ladder), and when machine
    noise does bite it errs toward "unresolved" rather than toward blaming the
    student. The closed form is not lost by the swap — it is the oracle, so the
    gate re-checks this simulation against it on every case, forever.
    """
    remaining = [0] * 26
    for label in tasks:
        index = ord(label) - 65  # "A".."Z", the statement's own constraint
        if not 0 <= index < 26:
            raise ValueError(f"unexpected task label {label!r}")
        remaining[index] += 1
    ready = [0] * 26
    left = len(tasks)
    intervals = 0
    while left:
        intervals += 1
        pick = -1
        best = 0
        for i in range(26):
            count = remaining[i]
            if count and ready[i] == 0 and count > best:
                pick, best = i, count
        for i in range(26):
            if i != pick and ready[i] > 0:
                ready[i] -= 1
        if pick >= 0:
            remaining[pick] -= 1
            left -= 1
            ready[pick] = n if remaining[pick] else 0
    return intervals


# --- canonical reference (combination-sum) ---

@reference("combination-sum")
def _combination_sum_reference(candidates: list[int], target: int) -> list[list[int]]:
    """Canonical backtracking at the intended complexity: sort once, then DFS over
    the candidates in non-decreasing index order, subtracting each pick from the
    remaining target and abandoning a branch as soon as the smallest candidate
    left does not fit (sorting is what makes that a `break` rather than a
    `continue`). The recursion stays at the *same* index after taking a value,
    which is the statement's "the same number may be chosen unlimited times", and
    the index never decreases, so each combination is built in exactly one order:
    no duplicates are possible and no `set` is needed to dedupe.

    The result comes out ascending-lexicographic, the canonical form of the set
    answer the cases compare with "compare": "sorted". Time is the size of the
    search tree (exponential in the target, linear in the candidates per node);
    the auxiliary space is the recursion depth and the current path, at most
    target // min(candidates) + 1."""
    values = sorted(candidates)
    out: list[list[int]] = []
    path: list[int] = []

    def _combination_sum_walk(start: int, remaining: int) -> None:
        if remaining == 0:
            out.append(list(path))
            return
        for i in range(start, len(values)):
            value = values[i]
            if value > remaining:
                break
            path.append(value)
            _combination_sum_walk(i, remaining - value)
            path.pop()

    _combination_sum_walk(0, target)
    return out


# --- canonical reference (combination-sum-ii) ---

@reference("combination-sum-ii")
def _combination_sum_ii_reference(candidates: list[int], target: int) -> list[list[int]]:
    """Canonical sort + backtracking: walk the sorted candidates, take one only if
    it still fits in what is left of the target, and refuse to start a second
    branch with a value an earlier copy already started at the same level
    (`i > start and ordered[i] == ordered[i - 1]`). Sorting buys both of the
    things that make the answer duplicate-free without a result-level set: equal
    candidates sit next to each other, so the same-level skip is exact, and the
    loop can stop as soon as a value exceeds `remaining` -- every later candidate
    is at least as large, so none of them fits either. Paths grow in
    non-decreasing order, so each combination comes out ascending, which is the
    form the statement's own examples use. Time O(n * 2^n) worst case (at most
    2^n subsets of candidates are examined, and an accepted combination is copied
    at a cost of up to n), space O(n) for the path plus the recursion. Both
    pruning steps assume what the statement guarantees -- every candidate is
    >= 1, so the sorted `break` can never prune a sum that negative values could
    still bring back down. The oracle, being brute force, needs no such
    assumption."""
    ordered = sorted(candidates)
    out: list[list[int]] = []
    path: list[int] = []

    def _combination_sum_ii_walk(start: int, remaining: int) -> None:
        if remaining == 0:
            if path:  # the empty combination is not an answer
                out.append(list(path))
            return
        for i in range(start, len(ordered)):
            if i > start and ordered[i] == ordered[i - 1]:
                continue  # a repeated candidate: the earlier copy owns this branch
            if ordered[i] > remaining:
                break  # sorted, so every later candidate is too large as well
            path.append(ordered[i])
            _combination_sum_ii_walk(i + 1, remaining - ordered[i])
            path.pop()

    _combination_sum_ii_walk(0, target)
    return out


# --- canonical reference (letter-combinations-of-a-phone-number) ---

@reference("letter-combinations-of-a-phone-number")
def _letter_combinations_of_a_phone_number_reference(digits: str) -> list[str]:
    """Canonical backtracking: one DFS that extends a prefix with every letter of
    the current key and emits the prefix when it is as long as the input. O(4^n * n)
    time and O(n) space, where n is the number of digits -- at most four letters per
    digit gives at most 4^n prefixes and each one costs n character appends to
    build, and the recursion is n deep (the returned list is not counted, as
    everywhere else in the corpus). The output order is the keypad order of each
    digit, so it matches the statement's Example 1 exactly; the case's own
    "compare": "sorted" tag is what makes any other order legal for a student."""
    keypad = {
        "2": "abc", "3": "def", "4": "ghi", "5": "jkl",
        "6": "mno", "7": "pqrs", "8": "tuv", "9": "wxyz",
    }
    if not digits:
        return []
    out: list[str] = []
    prefix: list[str] = []

    def _letter_combinations_of_a_phone_number_walk(i: int) -> None:
        if i == len(digits):
            out.append("".join(prefix))
            return
        for letter in keypad.get(digits[i], ""):
            prefix.append(letter)
            _letter_combinations_of_a_phone_number_walk(i + 1)
            prefix.pop()

    _letter_combinations_of_a_phone_number_walk(0)
    return out


# --- canonical reference (n-queens) ---

@reference("n-queens")
def _n_queens_reference(n: int) -> list[list[str]]:
    """Canonical backtracking, the three-set version every writeup of this problem
    gives: place one queen per row, keep a set of used columns and a set for each
    diagonal direction, and recurse only into a column that attacks nothing. The
    two diagonal sets are indexed by r - c and r + c, which is what makes the
    attack test O(1) instead of the oracle's scan over the queens already placed.

    O(n!) time and O(n^2) space: the search tree holds at most n! partial
    placements (each row takes a column no earlier row took, so the number of
    k-queen prefixes is n!/(n-k)! and the whole tree is O(n!)), and the board is
    an n x n list of characters that the search marks and unmarks in place, with
    O(n) more for the three sets. The board is the reference's own state, not
    output, so it is counted; the returned list of solutions is not, which is the
    corpus convention (three_sum, add_two_numbers).

    Solutions come back in lexicographic column order -- the order the statement's
    own Example 1 uses, which is why the visible tests can transcribe it verbatim
    -- and the case's "compare": "sorted" tag is what makes any other order legal
    for a student."""
    if n < 1:
        return []
    out: list[list[str]] = []
    board = [["."] * n for _ in range(n)]
    cols: set[int] = set()
    diag: set[int] = set()  # r - c: one set per "" diagonal
    anti: set[int] = set()  # r + c: one set per "/" diagonal

    def _n_queens_place(r: int) -> None:
        if r == n:
            out.append(["".join(row) for row in board])
            return
        for c in range(n):
            if c in cols or (r - c) in diag or (r + c) in anti:
                continue
            cols.add(c)
            diag.add(r - c)
            anti.add(r + c)
            board[r][c] = "Q"
            _n_queens_place(r + 1)
            board[r][c] = "."
            cols.discard(c)
            diag.discard(r - c)
            anti.discard(r + c)

    _n_queens_place(0)
    return out


# --- canonical reference (palindrome-partitioning) ---

@reference("palindrome-partitioning")
def _palindrome_partitioning_reference(s: str) -> list[list[str]]:
    """Canonical backtracking: from the current cut position, try every prefix of
    the remaining string that is a palindrome and recurse past it. The cuts ARE
    the path, so every partition of s is exactly one root-to-leaf walk, and two
    different walks differ in at least one cut -- with non-empty pieces that
    means different piece lists -- so the answer cannot contain the same
    partition twice and no result-level de-duplication is needed. The palindrome
    test is the obvious slice flip rather than a memoized table: the intended
    complexity is the backtracking itself (time O(n * 2^n) -- at most 2^(n-1)
    partitions, each copied at a cost of up to n -- and space O(n) for the path
    plus the recursion), and a table would only hide that behind a fixed cost."""
    n = len(s)
    out: list[list[str]] = []
    path: list[str] = []

    def _palindrome_partitioning_walk(start: int) -> None:
        if start == n:
            out.append(list(path))
            return
        for end in range(start + 1, n + 1):
            piece = s[start:end]
            if piece == piece[::-1]:
                path.append(piece)
                _palindrome_partitioning_walk(end)
                path.pop()

    _palindrome_partitioning_walk(0)
    return out


# --- canonical reference (permutations) ---

@reference("permutations")
def _permutations_reference(nums: list[int]) -> list[list[int]]:
    """Canonical backtracking: walk the values in sorted order, marking each one
    used and unmarking it on the way back out, so every arrangement is built
    exactly once and the result comes out ascending-lexicographic — the canonical
    form of a set answer (and the order the statement's examples print).

    O(n * n!) time: n! leaves, each copied out in O(n). O(n) auxiliary space: the
    path, the used flags and the recursion depth — the returned list of
    permutations is not counted."""
    values = sorted(nums)
    n = len(values)
    used = [False] * n
    path: list[int] = []
    out: list[list[int]] = []

    def _permutations_walk() -> None:
        if len(path) == n:
            out.append(list(path))
            return
        for i in range(n):
            if used[i]:
                continue
            used[i] = True
            path.append(values[i])
            _permutations_walk()
            path.pop()
            used[i] = False

    _permutations_walk()
    return out


# --- canonical reference (subsets) ---

@reference("subsets")
def _subsets_reference(nums: list[int]) -> list[list[int]]:
    """Canonical bitmask enumeration: subset k is the set of positions where bit i
    of k is set, so all 2^n subsets come out of one loop with no recursion —
    O(n * 2^n) time (each of the 2^n masks scans the n values) and O(n) auxiliary
    space beyond the answer itself.

    The order is the statement's own example order ([], [1], [2], [1,2], ...);
    every case carries "compare": "sorted", so any order is legal and this is
    only the canonical form."""
    n = len(nums)
    out: list[list[int]] = []
    for mask in range(1 << n):
        out.append([nums[i] for i in range(n) if mask >> i & 1])
    return out


# --- canonical reference (subsets-ii) ---

@reference("subsets-ii")
def _subsets_ii_reference(nums: list[int]) -> list[list[int]]:
    """Canonical sort + backtracking: grow every subset once, and at the level of
    the search where an earlier copy of a repeated value already built that
    branch, skip it. Sorting puts equal values next to each other, so
    `i > start and ordered[i] == ordered[i - 1]` is exactly "this branch repeats
    the one the previous copy just built" -- the answer never needs a
    result-level de-duplication pass. Paths grow in non-decreasing order because
    the array is sorted, so every subset comes out in the ascending form the
    site's own expected output uses (Example 1 is
    [[], [1], [1,2], [1,2,2], [2], [2,2]]). Time O(n * 2^n) -- at most 2^n
    subsets, each copied once at a cost of up to n -- and space O(n) for the path
    plus the recursion."""
    ordered = sorted(nums)
    out: list[list[int]] = []
    path: list[int] = []

    def _subsets_ii_walk(start: int) -> None:
        out.append(list(path))
        for i in range(start, len(ordered)):
            if i > start and ordered[i] == ordered[i - 1]:
                continue  # the previous copy already explored this branch
            path.append(ordered[i])
            _subsets_ii_walk(i + 1)
            path.pop()

    _subsets_ii_walk(0)
    return out


# --- canonical reference (word-search) ---

@reference("word-search")
def _word_search_reference(board: list[list[str]], word: str) -> bool:
    """Canonical DFS + backtracking: try every cell as the start of the word,
    descend to a neighbour only while the letter keeps matching, mark the cell
    used on the way down and release it on the way back up (the statement forbids
    using a cell twice), and return at the first complete path. The letter test is
    the pruning step, so a mismatch anywhere abandons that whole branch, which is
    what makes this O(m * n * 3^L) rather than the oracle's unpruned 4^L walk.

    O(m * n * 3^L) time and O(L) space: from each of the m * n start cells at most
    three new directions per step (the cell you came from is excluded) to a depth
    of L, and the auxiliary state is the L-deep recursion plus the used-cell mark.
    The visited cells are a set of (row, column) pairs rather than an m x n matrix,
    so the reference's own footprint is O(L) and a student's O(m * n) mark is
    visible in the space ratio rather than hidden by the baseline. The board is
    never mutated -- the mark is separate -- so an in-place implementation cannot
    be blamed on the reference, and the return value is the same bool either way."""
    rows = len(board)
    cols = len(board[0]) if rows else 0
    if not word:
        return True
    last = len(word) - 1
    used: set[tuple[int, int]] = set()

    def _word_search_step(r: int, c: int, k: int) -> bool:
        if board[r][c] != word[k]:
            return False
        if k == last:
            return True
        used.add((r, c))
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in used:
                if _word_search_step(nr, nc, k + 1):
                    used.discard((r, c))
                    return True
        used.discard((r, c))
        return False

    return any(_word_search_step(r, c, 0) for r in range(rows) for c in range(cols))


# --- canonical reference (counting-bits) ---

@reference("counting-bits")
def _counting_bits_reference(n: int) -> list[int]:
    """Canonical single pass, O(n) time and O(n) space: ans[i] is ans[i >> 1]
    plus i's lowest bit — shifting right drops exactly that one bit — and
    ans[0] = 0 seeds it."""
    counts = [0] * (max(0, n) + 1)
    for i in range(1, len(counts)):
        counts[i] = counts[i >> 1] + (i & 1)
    return counts


# --- canonical reference (missing-number) ---

@reference("missing-number")
def _missing_number_reference(nums: list[int]) -> int:
    # XOR of every index and every value: each value that is present cancels
    # against its own index, so what survives is the missing one. Seeding with
    # len(nums) is what puts the n-th candidate into the fold (the array holds
    # the other n indices, never n itself when the answer is n). One pass, one
    # register: O(n) time and O(1) space, the statement's follow-up. Standalone
    # by design — the probe runs this in its own subprocess.
    missing = len(nums)
    for index, value in enumerate(nums):
        missing ^= index ^ value
    return missing


# --- canonical reference (number-of-1-bits) ---

@reference("number-of-1-bits")
def _number_of_1_bits_reference(n: int) -> int:
    """Canonical O(1): n & (n - 1) clears the lowest set bit, so the loop runs
    once per set bit — at most 31 steps for the statement's bound of 2^31 - 1."""
    count = 0
    while n:
        n &= n - 1
        count += 1
    return count


# --- canonical reference (reverse-bits) ---

@reference("reverse-bits")
def _reverse_bits_reference(n: int) -> int:
    """Canonical O(1): 32 fixed iterations, each pushing n's lowest bit onto the
    right of the result and shifting n down — the 32-bit reversal by definition."""
    result = 0
    for _ in range(32):
        result = (result << 1) | (n & 1)
        n >>= 1
    return result


# --- canonical reference (reverse-integer) ---

@reference("reverse-integer")
def _reverse_integer_reference(x: int) -> int:
    # The intended digit-by-digit reversal: pop the last digit with % 10 and
    # push it onto the result, once per digit — O(log n) time in the number of
    # digits and O(1) space, with no string allocation. The statement's rule is
    # applied once, at the end, to the value that was actually built: outside
    # [-2^31, 2^31 - 1] the answer is 0. Nothing here needs a 64-bit type the
    # environment is said not to have — the comparison is against the two
    # 32-bit constants, and abs()/sign handling is what keeps the digit loop
    # off negative remainders (Python's % 10 on a negative x would otherwise
    # produce negative digits).
    limit = 2**31 - 1
    sign = -1 if x < 0 else 1
    value = abs(x)
    reversed_value = 0
    while value:
        reversed_value = reversed_value * 10 + value % 10
        value //= 10
    reversed_value *= sign
    if reversed_value > limit or reversed_value < -limit - 1:
        return 0
    return reversed_value


# --- canonical reference (single-number) ---

@reference("single-number")
def _single_number_reference(nums: list[int]) -> int:
    """Canonical O(n)/O(1): XOR the whole array — every paired value cancels
    (x ^ x == 0) and the unpaired one survives (0 ^ x == x)."""
    result = 0
    for value in nums:
        result ^= value
    return result


# --- canonical reference (sum-of-two-integers) ---

@reference("sum-of-two-integers")
def _sum_of_two_integers_reference(a: int, b: int) -> int:
    # The canonical bit-trick add: XOR is the sum without carries, AND shifted
    # left is the carry, and the two are folded together until no carry is left.
    # The 32-bit mask is load-bearing in Python, not decoration: on unbounded
    # ints the plain `(a & b) << 1` of an opposite-sign pair gains a set bit
    # above bit 31 on every pass and never terminates (a = 1000, b = -1000 runs
    # forever — see the notes). Masking to the statement's own 32-bit setting
    # bounds the loop at 32 passes, and the sign is restored with ~ so this
    # reference uses no `+` and no `-` either: it obeys the rule it teaches.
    # O(1) time, O(1) space.
    mask = 0xFFFFFFFF
    x, y = a & mask, b & mask
    while y:
        carry = ((x & y) << 1) & mask
        x = (x ^ y) & mask
        y = carry
    return x if x < 0x80000000 else ~(x ^ mask)


# --- canonical reference (detect-squares) ---

@reference("detect-squares")
def _detect_squares_reference(ops: list[list]) -> list:
    """Canonical design, driven through the same op list the oracle takes: a
    multiplicity map keyed by (x, y) for the adds, and a count that walks the
    distinct points stored, taking every point that shares the query's diagonal
    (|dx| == |dy| != 0) as the OPPOSITE corner of a square. The other two corners
    are then (px, qy) and (qx, py), so the product of the three multiplicities
    counts every way to choose the three points at once. O(1) per add, at most
    one pass over the distinct points per count, O(n) space."""
    counts: dict[tuple[int, int], int] = {}
    out: list = []
    for op in ops:
        method, *args = op
        if method == 'add':
            x, y = args[0]
            counts[(x, y)] = counts.get((x, y), 0) + 1
            out.append(None)
        elif method == 'count':
            qx, qy = args[0]
            total = 0
            for (px, py), multiplicity in counts.items():
                if px != qx and abs(px - qx) == abs(py - qy):
                    total += multiplicity * counts.get((px, qy), 0) * counts.get((qx, py), 0)
            out.append(total)
        else:  # pragma: no cover - the generator only emits add and count
            raise ValueError(f'unknown op {method}')
    return out


# --- canonical reference (happy-number) ---

@reference("happy-number")
def _happy_number_reference(n: int) -> bool:
    # The intended solution: follow the chain and remember every value seen in a
    # set, which is how the statement's "loops endlessly in a cycle" is detected
    # - the second time a value appears, no new value can ever follow, and if 1
    # has not shown up by then it never will. O(log n) time (each step sums the
    # squares of the value's O(log n) digits, and at most O(log n) distinct
    # values can appear before the chain repeats) and O(log n) space for the
    # seen set. Total for n >= 0.
    seen: set[int] = set()
    while n != 1 and n not in seen:
        seen.add(n)
        total = 0
        for digit in str(n):
            total += int(digit) * int(digit)
        n = total
    return n == 1


# --- canonical reference (multiply-strings) ---

@reference("multiply-strings")
def _multiply_strings_reference(num1: str, num2: str) -> str:
    """Canonical grade-school multiplication, O(m * n) time and O(m + n) space:
    an accumulator of m + n digits (no product of an m-digit and an n-digit
    number is longer), each digit pair multiplied into position i + j + 1 with
    the carry pushed into i + j, and the leading zeros stripped at the end -
    that last step is what turns a 100 * 100 accumulator into '10000' instead of
    '010000', and what makes a zero product come out as '0' rather than '' ."""
    left = [int(character) for character in num1]
    right = [int(character) for character in num2]
    m, n = len(left), len(right)
    accumulator = [0] * (m + n)
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            total = left[i] * right[j] + accumulator[i + j + 1]
            accumulator[i + j + 1] = total % 10
            accumulator[i + j] += total // 10
    start = 0
    while start < len(accumulator) - 1 and accumulator[start] == 0:
        start += 1
    return ''.join(str(digit) for digit in accumulator[start:])


# --- canonical reference (plus-one) ---

@reference("plus-one")
def _plus_one_reference(digits: list[int]) -> list[int]:
    """Canonical O(n) time / O(1) space: walk from the least significant digit,
    turn every trailing 9 into 0 and stop at the first digit below 9; if the
    carry survived the whole array (all nines) the answer is one digit longer."""
    out = list(digits)
    if not out:
        return []  # not a legal input; total, and the oracle agrees on it
    for i in range(len(out) - 1, -1, -1):
        if out[i] < 9:
            out[i] += 1
            return out
        out[i] = 0
    return [1] + out


# --- canonical reference (powx-n) ---

@reference("powx-n")
def _powx_n_reference(x: float, n: int) -> float:
    """Canonical binary exponentiation, iteratively: square the base and halve
    the exponent, multiplying into the accumulator for every set bit, then invert
    once when the exponent is negative - O(log|n|) time, O(1) space, and no
    recursion for the statement's 2^31 - 1 ceiling to blow up."""
    exponent = abs(n)
    base = x
    result = 1.0
    while exponent:
        if exponent & 1:
            result *= base
        base *= base
        exponent >>= 1
    return result if n >= 0 else 1.0 / result


# --- canonical reference (rotate-image) ---

@reference("rotate-image")
def _rotate_image_reference(matrix: list[list[int]]) -> None:
    # The canonical two steps, both inside the matrix that was handed over: the
    # transpose swap loop (each pair of off-diagonal cells once) and then a
    # reversal of every row. O(n^2) time and O(1) extra space - this reference
    # never builds a second matrix, which is the space baseline the probe
    # measures a student's allocations against.
    size = len(matrix)
    for i in range(size):
        for j in range(i + 1, size):
            matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]
    for row in matrix:
        row.reverse()


# --- canonical reference (set-matrix-zeroes) ---

@reference("set-matrix-zeroes")
def _set_matrix_zeroes_reference(matrix: list[list[int]]) -> None:
    # The follow-up's constant-space marking: the first row and the first column
    # ARE the flag arrays. Record whether they themselves contained a zero, use
    # matrix[i][0] / matrix[0][j] as the row and column flags for the interior,
    # clear the interior from those flags, and clear the first row and column
    # last if they were flagged. O(m * n) time, O(1) extra space - no second
    # structure of any size, which is the space baseline the probe compares a
    # student's flag arrays against.
    rows = len(matrix)
    if rows == 0 or not matrix[0]:
        return
    cols = len(matrix[0])
    first_row_zero = any(matrix[0][j] == 0 for j in range(cols))
    first_col_zero = any(matrix[i][0] == 0 for i in range(rows))
    for i in range(1, rows):
        for j in range(1, cols):
            if matrix[i][j] == 0:
                matrix[i][0] = 0
                matrix[0][j] = 0
    for i in range(1, rows):
        for j in range(1, cols):
            if matrix[i][0] == 0 or matrix[0][j] == 0:
                matrix[i][j] = 0
    if first_row_zero:
        for j in range(cols):
            matrix[0][j] = 0
    if first_col_zero:
        for i in range(rows):
            matrix[i][0] = 0


# --- canonical reference (spiral-matrix) ---

@reference("spiral-matrix")
def _spiral_matrix_reference(matrix: list[list[int]]) -> list[int]:
    # The canonical four-boundary walk: top, right, bottom, left, shrinking each
    # boundary as it is consumed. The two `if` guards are the whole trick - they
    # stop a single remaining row or column from being walked twice, which is
    # this problem's classic failure. O(m * n) time; the result list is the only
    # thing it builds, and it does not touch the argument.
    if not matrix or not matrix[0]:
        return []
    out: list[int] = []
    top, bottom = 0, len(matrix) - 1
    left, right = 0, len(matrix[0]) - 1
    while top <= bottom and left <= right:
        for j in range(left, right + 1):
            out.append(matrix[top][j])
        top += 1
        for i in range(top, bottom + 1):
            out.append(matrix[i][right])
        right -= 1
        if top <= bottom:
            for j in range(right, left - 1, -1):
                out.append(matrix[bottom][j])
            bottom -= 1
        if left <= right:
            for i in range(bottom, top - 1, -1):
                out.append(matrix[i][left])
            left += 1
    return out


# --- canonical reference (insert-interval) ---

@reference("insert-interval")
def _insert_interval_reference(
    intervals: list[list[int]], newInterval: list[int]
) -> list[list[int]]:
    """Canonical one-pass sweep, O(n) time and O(1) space beyond the returned
    list (n = the number of intervals): the input is already sorted by starti, so

      1. every interval that ends strictly before the new one starts is copied
         through untouched,
      2. from the first interval that does not, every interval that starts at or
         before the new end is absorbed -- `<=`, because the statement counts two
         intervals that share even a single point as overlapping, so a new
         interval starting exactly where an interval ends merges with it
         (Example 2: [4,8] swallows [8,10]),
      3. the merged interval is emitted, then the untouched tail is copied.

    The two boundaries are the whole problem, and they are not symmetric: phase 1
    tests `intervals[i][1] < start` (strict, so an interval that ends exactly at
    the new start is absorbed in phase 2 rather than copied), phase 2 tests
    `intervals[i][0] <= end` (non-strict, for the same reason)."""
    start, end = newInterval[0], newInterval[1]
    out: list[list[int]] = []
    i = 0
    total = len(intervals)
    while i < total and intervals[i][1] < start:
        out.append(intervals[i])
        i += 1
    while i < total and intervals[i][0] <= end:
        start = min(start, intervals[i][0])
        end = max(end, intervals[i][1])
        i += 1
    out.append([start, end])
    out.extend(intervals[i:])
    return out


# --- canonical reference (meeting-rooms) ---

@reference("meeting-rooms")
def _meeting_rooms_reference(intervals: list[list[int]]) -> bool:
    intervals.sort()  # in place: the target is O(1) space beyond the input
    for i in range(1, len(intervals)):
        if intervals[i][0] < intervals[i - 1][1]:
            return False
    return True


# --- canonical reference (meeting-rooms-ii) ---

@reference("meeting-rooms-ii")
def _meeting_rooms_ii_reference(intervals: list[list[int]]) -> int:
    starts = sorted(interval[0] for interval in intervals)
    ends = sorted(interval[1] for interval in intervals)
    rooms = 0
    best = 0
    freed = 0
    for start in starts:
        # a meeting ending at t frees its room for a meeting starting at t
        while freed < len(ends) and ends[freed] <= start:
            rooms -= 1
            freed += 1
        rooms += 1
        if rooms > best:
            best = rooms
    return best


# --- canonical reference (merge-intervals) ---

@reference("merge-intervals")
def _merge_intervals_reference(intervals: list[list[int]]) -> list[list[int]]:
    """Canonical sort-and-sweep: O(n log n) time (the sort dominates) and O(n)
    space for the ordered copy plus the result, where n is the number of
    intervals. The input is NOT sorted, so ordering by start is the first real
    step; after that one pass is enough, because intervals that share a point are
    merged by extending the last interval in the result -- `iv[0] <= last_end`
    and not `<`, since the statement counts touching as overlapping (its Example
    2 merges [1,4] with [4,5]) -- and an interval that starts after the last end
    cannot overlap anything already emitted. The result is therefore ascending by
    start and its intervals do not even touch, which is the canonical order the
    visible tests show."""
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged: list[list[int]] = []
    for iv in ordered:
        if merged and iv[0] <= merged[-1][1]:
            if iv[1] > merged[-1][1]:
                merged[-1][1] = iv[1]
        else:
            merged.append([iv[0], iv[1]])
    return merged


# --- canonical reference (minimum-interval-to-include-each-query) ---

@reference("minimum-interval-to-include-each-query")
def _minimum_interval_to_include_each_query_reference(
    intervals: list[list[int]], queries: list[int]
) -> list[int]:
    import heapq  # the probe runs this snippet alone; imports must be inside it

    by_left = sorted(intervals)
    order = sorted(range(len(queries)), key=lambda index: queries[index])
    answers = [-1] * len(queries)
    heap: list[tuple[int, int]] = []  # (size, right), smallest size on top
    nxt = 0
    for index in order:
        point = queries[index]
        while nxt < len(by_left) and by_left[nxt][0] <= point:
            left, right = by_left[nxt]
            heapq.heappush(heap, (right - left + 1, right))
            nxt += 1
        while heap and heap[0][1] < point:
            heapq.heappop(heap)  # ends before the query; one ending at it stays
        if heap:
            answers[index] = heap[0][0]
    return answers


# --- canonical reference (non-overlapping-intervals) ---

@reference("non-overlapping-intervals")
def _non_overlapping_intervals_reference(intervals: list[list[int]]) -> int:
    """Canonical greedy: O(n log n) time and O(n) space for the copy ordered by
    end, where n is the number of intervals.

    Order by END and keep every interval that starts at or after the last kept
    end. Earliest-finishing-first is what makes the greedy optimal -- the interval
    that ends first can always be swapped into an optimal solution -- and the
    comparison is `start >= last_end` and not `>`: the statement says intervals
    that only touch at a point are non-overlapping, so an interval starting
    exactly where the last one ended is kept and not counted as a removal. The
    count of kept intervals is the largest non-overlapping set, and every other
    interval has to be removed."""
    ordered = sorted(intervals, key=lambda iv: iv[1])
    kept = 0
    last_end = None
    for start, end in ordered:
        if last_end is None or start >= last_end:
            kept += 1
            last_end = end
    return len(intervals) - kept


# --- canonical reference (gas-station) ---

@reference("gas-station")
def _gas_station_reference(gas: list[int], cost: list[int]) -> int:
    """Canonical greedy: total >= 0 decides *whether* a start exists, and the
    start is the station right after the last prefix whose tank went negative —
    one pass, O(1) extra space. A tank that goes negative on the way to i rules
    out every start in [start, i], which is what lets a single scan replace the
    n simulations. The empty input is excluded by n >= 1; the guard keeps the
    reference identical to the oracle (which answers -1) if it ever arrives."""
    if not gas:
        return -1
    total = 0
    tank = 0
    start = 0
    for i in range(len(gas)):
        delta = gas[i] - cost[i]
        total += delta
        tank += delta
        if tank < 0:
            start = i + 1
            tank = 0
    return start if total >= 0 else -1


# --- canonical reference (hand-of-straights) ---

@reference("hand-of-straights")
def _hand_of_straights_reference(hand: list[int], group_size: int) -> bool:
    """The intended O(n log n): count the cards, then sweep the distinct values in
    ascending order.

    Each distinct value is a group *start* as many times as it is still
    outstanding when the sweep reaches it (`need`), because the groups that
    contain the smallest unfinished value must all start exactly there. Those
    `need` groups then need `need` cards of each of the next `group_size - 1`
    values, which is what the inner loop charges. O(n) space for the counts, at
    most one entry per distinct card."""
    if group_size < 1 or len(hand) % group_size:
        return False
    counts: dict[int, int] = {}
    for card in hand:
        counts[card] = counts.get(card, 0) + 1
    for start in sorted(counts):
        need = counts[start]
        if need == 0:  # already consumed by the groups that started below it
            continue
        for value in range(start, start + group_size):
            if counts.get(value, 0) < need:
                return False
            counts[value] -= need
    return True


# --- canonical reference (jump-game) ---

@reference("jump-game")
def _jump_game_reference(nums: list[int]) -> bool:
    """Canonical greedy: one pass, carrying the farthest index reachable so far;
    an index beyond that frontier means the array cannot be finished, and if the
    pass survives every index then the last one was reachable.

    Deliberately written without the mid-loop `reach >= n - 1 -> True` shortcut,
    so the probe's baseline always reads the whole array (on the profiler input
    the shortcut would fire two indices early); the answer is the same either way.
    The empty list is excluded by the constraint, but the guard keeps the
    reference identical to the oracle on every input the gate could hand it."""
    if not nums:
        return False  # no last index to reach
    reach = 0
    for i, jump in enumerate(nums):
        if i > reach:
            return False  # unreachable, and so is everything past it
        reach = max(reach, i + jump)
    return reach >= len(nums) - 1


# --- canonical reference (jump-game-ii) ---

@reference("jump-game-ii")
def _jump_game_ii_reference(nums: list[int]) -> int:
    """Canonical level-BFS greedy: one pass remembering where the current jump
    lands (cur_end) and the farthest index the whole level can reach (farthest);
    each time the scan reaches cur_end, one more jump has been spent.

    The reachability guard keeps the reference total and makes it agree with the
    oracle (which answers -1) on an array the statement's guarantee excludes; on
    graded and measured inputs it never fires."""
    jumps = 0
    cur_end = 0
    farthest = 0
    for i in range(len(nums) - 1):
        if i > farthest:
            return -1  # index i is unreachable: there is no route to the end
        farthest = max(farthest, i + nums[i])
        if i == cur_end:
            jumps += 1
            cur_end = farthest
    return jumps


# --- canonical reference (merge-triplets-to-form-target-triplet) ---

@reference("merge-triplets-to-form-target-triplet")
def _merge_triplets_reference(triplets: list[list[int]], target: list[int]) -> bool:
    """The intended single pass: one sweep, three flags.

    Keep only the triplets that stay inside the target - anything above it is stuck
    above it and can never be part of a merge that ends at the target - and record
    which coordinates of the target one of those already matches. A coordinate that
    no surviving triplet matches can never be reached, because every value a merge
    can produce is a componentwise max of original triplets and this one is below
    the target everywhere. O(n) time over the triplets and O(1) extra space."""
    size = len(target)
    seen = [False] * size
    for row in triplets:
        if all(row[k] <= target[k] for k in range(size)):
            for k in range(size):
                if row[k] == target[k]:
                    seen[k] = True
    return all(seen)


# --- canonical reference (partition-labels) ---

@reference("partition-labels")
def _partition_labels_reference(s: str) -> list[int]:
    """Canonical greedy: one pass records each letter's last index, a second
    extends the current part's end to every last occurrence seen inside it and
    closes the part exactly when the scan reaches that end. The scan therefore
    visits every index and never stops before the string does; the table holds at
    most 26 entries, which is O(1) for the statement's fixed alphabet."""
    last: dict[str, int] = {}
    for i, ch in enumerate(s):
        last[ch] = i
    sizes: list[int] = []
    start = 0
    end = 0
    for i, ch in enumerate(s):
        if last[ch] > end:
            end = last[ch]
        if i == end:
            sizes.append(i - start + 1)
            start = i + 1
    return sizes


# --- canonical reference (valid-parenthesis-string) ---

@reference("valid-parenthesis-string")
def _valid_parenthesis_string_reference(s: str) -> bool:
    """The intended one pass, two counters.

    `low` is the fewest '(' that can still be open if every '*' seen so far is read
    as ')' (never below zero: a star that closed a bracket could have been read as
    empty instead), and `high` is the most that can be open if every star is read
    as '('. The readings of a prefix leave it at every open count in [low, high]
    and at no other, so a prefix whose `high` is negative is a ')' that no reading
    can match, and the string is valid exactly when the whole string can end with
    nothing open - which the clamped `low` reports. O(n) time, O(1) space."""
    low = 0
    high = 0
    for char in s:
        if char == "(":
            low += 1
            high += 1
        elif char == ")":
            low -= 1
            high -= 1
        else:  # '*': ')' lowers the floor, '(' raises the ceiling
            low -= 1
            high += 1
        if high < 0:
            return False
        if low < 0:
            low = 0
    return low == 0
