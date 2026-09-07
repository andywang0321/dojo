"""
Maximum Subarray Sum [Easy]

Given an integer array, find the largest sum of any contiguous subarray
within the array. If every element is negative, return 0 (the empty subarray
is allowed).

Example 1:
Input: [-1, -3, 5, -4, 3, -6, 9, 2]
Output: 11
Explanation: the subarray [9, 2] sums to 11.

Example 2:
Input: [-1, -5, -3, -7]
Output: 0
Explanation: every element is negative, so the empty subarray wins.

You should aim for a solution with O(n) time and O(1) space, where n is the
length of the array.
"""


def sum_largest_subarray(A: list[int]) -> int:
    sum, max_sum = 0, 0
    for a in A:
        if a >= 0:
            sum += a
        if sum > max_sum:
            max_sum = sum
        if a < 0:
            sum = 0
    return max_sum


def main() -> None:
    A = [-1, -3, 5, -4, 3, -6, 9, 2]
    B = [-1, -5, -3, -7]
    assert sum_largest_subarray(A) == 11, "Case A failed!"
    assert sum_largest_subarray(B) == 0, "Case B failed!"
    print("All tests passed!")


if __name__ == "__main__":
    main()
