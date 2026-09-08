"""
Array Intersection [Easy]

Given two arrays of integers, return their intersection: the values that
appear in both arrays, without duplicates, sorted in ascending order.

Example 1:
Input: A = [1, 2, 3, 4, 5], B = [0, 1, 3, 7]
Output: [1, 3]

Example 2:
Input: A = [1, 2, 3, 4, 5], B = [6, 7]
Output: []

You should aim for a solution with O(n) time and O(n) space, where n is the
total number of elements across both arrays.
"""

from typing import Any, List


def intersection(A: List[Any], B: List[Any]) -> List[Any]:
    return list(set(A) & set(B))


def main() -> None:
    A = [1, 2, 3, 4, 5]
    B = [0, 1, 3, 7]
    assert intersection(A, B) == [1, 3], "intersection failed!"
    assert intersection(A, [6, 7]) == [], "disjoint case failed!"
    print("All tests passed!")


if __name__ == "__main__":
    main()
