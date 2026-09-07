# Facebook: Given a list of coordinates, write a function to find the k closest points (measured by Euclidean distance) to the origin. For example, if k = 3, and the points are [[2, -1], [3, 2], [4, 1], [-1, -1], [-2, 2]], then return [[-1, -1], [2, -1], [-2, 2]].

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
