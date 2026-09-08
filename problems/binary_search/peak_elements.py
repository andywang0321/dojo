"""
Find a Peak Element [Medium]

Given an array of positive integers, a peak element is one that is greater
than both of its neighbors (an endpoint only needs to beat its single
neighbor). Return the index of the leftmost peak element in the array.

Example 1:
Input: [3, 5, 2, 4, 1]
Output: 1
Explanation: 1 (value 5) and 3 (value 4) are both peaks; 1 is the leftmost.

Example 2:
Input: [4, 3, 2, 1]
Output: 0

Example 3:
Input: [1, 2, 3, 4]
Output: 3

You should aim for a solution with O(log n) time and O(1) space, where n is
the length of the array. (Why does comparing an element with one neighbor
always let you halve the search space?)
"""


def find_a_peak(A: list[int]) -> int:
    """
    binary search to find peak
    Idea:
        Go to mid. If left > mid, then there must be a peak to left. Set mid as end.
        Otherwise, if right > mid, then there must be a peak to the right. Set mid as start.
        If left < mid > right, then mid is a peak. Return mid.
    """
    start: int = 0
    end: int = len(A) - 1
    while True:
        mid = (start + end) // 2
        left = A[mid - 1] if mid - 1 >= 0 else 0
        right = A[mid + 1] if mid + 1 < len(A) else 0
        if left < A[mid] and A[mid] > right:
            return mid
        elif left > A[mid]:
            end = mid - 1
        else:
            start = mid + 1


def main() -> None:
    A: list = [3, 5, 2, 4, 1]
    assert find_a_peak(A) == 1, "Random case failed!"
    B: list = [4, 3, 2, 1]
    assert find_a_peak(B) == 0, "Decreasing case failed!"
    C: list = [1, 2, 3, 4]
    assert find_a_peak(C) == 0, "Increasing case failed!"
    print("All tests passed!")


if __name__ == "__main__":
    main()
