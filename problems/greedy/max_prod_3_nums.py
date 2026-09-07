"""
Maximum Product of Three Numbers [Easy]

Given an integer array with at least three elements, return the maximum
product of any three numbers in the array. Elements may be negative, and the
answer itself may be negative.

Example 1:
Input: A = [1, 3, 4, 5]
Output: 60
Explanation: 3 * 4 * 5 = 60.

Example 2:
Input: B = [-2, -4, 5, 3]
Output: 40
Explanation: -2 * -4 * 5 = 40 — two large negatives can beat two positives.

You should aim for a solution with O(n log n) time and O(1) space, where n is
the length of the array. (A single pass tracking the three largest and two
smallest values gives O(n) time.)
"""

from typing import List, Any
import heapq

def max_tri_prod(A: List[int]) -> int:
    assert len(A) >= 3, 'len(input) must be >= 3!'
    largest = heapq.nlargest(3, A)
    smallest = heapq.nsmallest(2, A)
    return max(
        largest[0] * largest[1] * largest[2],
        smallest[0] * smallest[1] * largest[0]
    )

def main() -> None:
    A = [1, 3, 4, 5]
    B = [-2, -4, 5, 3]
    assert max_tri_prod(A) == 60, 'positive case failed!'
    assert max_tri_prod(B) == 40, 'negative case failed!'
    print('All tests passed!')

if __name__ == '__main__':
    main()
