"""Registries for oracles, judge-case generators, and profiler inputs.

ORACLES ARE REFERENCE IMPLEMENTATIONS. They exist only to produce expected
outputs for correctness testing. Never feed oracle code to the tutor agent —
the never-solve guarantee depends on reference solutions staying out of the
tutor's context.

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
    """A complete binary tree with exactly n nodes, nested-list form."""
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
