# D.E. Shaw: Given a target number, generate a random sample of n integers that sum to that target that also are within standard deviation sigma of the mean.


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
