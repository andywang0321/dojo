"""Visible checks for `has_pair` — the student runs these.

They are shipped to the student and appear in their workbench, so they must be
honest: they check the statement's promises and nothing more.
"""

from has_pair import has_pair


def check() -> None:
    assert has_pair([3, 1, 4, 1, 5], 6) is True, "a pair exists"
    assert has_pair([3, 1, 4], 8) is False, "no pair sums to 8"
    assert has_pair([2, 2], 4) is True, "equal values at different indices count"
    assert has_pair([], 0) is False, "an empty list has no pair"
    assert has_pair([0], 0) is False, "one index cannot be used twice"
    print("all checks passed")


if __name__ == "__main__":
    check()
