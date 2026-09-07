"""
Kth Smallest Element in a Sorted Matrix [Easy]

Given an n x n matrix whose rows and columns are each sorted in ascending
order, return the k-th smallest element in the matrix (1-indexed).

Example 1:
Input:
matrix = [[1, 4, 7],
          [3, 5, 9],
          [6, 8, 11]]
k = 4
Output: 5
Explanation: the elements in sorted order are [1, 3, 4, 5, 6, 7, 8, 9, 11];
the 4th is 5.

Constraints:
1 <= k <= n * n

Both rows and columns are sorted — a heap over the first k rows and columns
avoids flattening and sorting the entire matrix.
"""

from heapq import heappush


def k_smallest(k: int, A: list[list[int]]) -> float:
    min_heap: list = []
    for row in A[:k]:
        for a in row[:k]:
            heappush(min_heap, a)
    return min_heap[k]


def main() -> None:
    A = [[1, 4, 7], [3, 5, 9], [6, 8, 11]]
    assert k_smallest(4, A) == 5, "Test case failed!"
    print("All tests passed!")


if __name__ == "__main__":
    main()
