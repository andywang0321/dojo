"""
Generate Sample Summing to a Target [Medium]

Given a target integer, a sample size n, and a real number sigma >= 0,
generate a list of exactly n integers such that:

- the elements sum exactly to the target, and
- the sample's standard deviation does not exceed sigma.

The generator may be random — any list meeting both conditions is a correct
answer. Different runs may return different lists.

Example 1:
Input: n = 5, sigma = 3.6, target = 6
Output: any list of 5 integers summing to 6 whose standard deviation is at
most 3.6.
"""


def mean(A: list) -> float:
    return sum(A) / len(A)


def sd(A: list) -> float:
    mu = mean(A)
    A_centered = [a - mu for a in A]
    var = mean(A_centered)
    return var**0.5


import random


def generate_sample(n: int, sigma: float, target: int) -> list:
    mu: float = target / n
    sd: int = int(sigma * mu)
    min_val, max_val = int(mu - sd), int(mu + sd)
    out = [min_val] * n
    remaining = target - n * min_val

    while remaining > 0:
        a = random.randint(0, n - 1)
        if out[a] >= max_val:
            continue
        out[a] += min(remaining, 1)
        remaining -= 1
    return out


def test_condition(sample: list, n: int, sigma: float, target: int) -> bool:
    length_check: bool = len(sample) == n
    sd_check: bool = sd(sample) - sigma < 1e-6
    target_check: bool = sum(sample) == target
    return length_check and sd_check and target_check


def main() -> None:
    n1, sig1, target1 = 5, 3.6, 6
    sample1 = generate_sample(n1, sig1, target1)
    assert test_condition(sample1, n1, sig1, target1), "Case 1 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    main()
