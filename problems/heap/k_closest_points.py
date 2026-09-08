"""
K Closest Points to Origin [Easy]

Given a list of points on the 2D plane and an integer k, return the k points
closest to the origin (0, 0), measured by Euclidean distance. Ties may be
broken in any order.

Example 1:
Input: k = 3, points = [[2, -1], [3, 2], [4, 1], [-1, -1], [-2, 2]]
Output: [[-1, -1], [2, -1], [-2, 2]]
Explanation: these are the three points with the smallest distance from the
origin.

Constraints:
1 <= k <= number of points

You should aim for a solution with O(n log n) time and O(k) space, where n
is the number of points. (A size-k heap gives O(n log k) time.)
"""

from typing import List
from heapq import heappush, heappop

def dist_to_origin(point: List[int]) -> float:
    return sum([i**2 for i in point])**0.5

def k_closest(k:int, points: List[List[int]]) -> List[List[int]]:
    min_heap = []
    for point in points:
        heappush(min_heap, (dist_to_origin(point), point))
    return [heappop(min_heap)[1] for _ in range(k)]

def main() -> None:
    points = [[2, -1], [3, 2], [4, 1], [-1, -1], [-2, 2]]
    assert k_closest(3, points) == [[-1, -1], [2, -1], [-2, 2]], 'failed!'
    print('All tests passed!')

if __name__ == "__main__":
    main()
