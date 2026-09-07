# Google: Say you have an n-by-n matrix of elements that are sorted in ascending order both in the columns and rows of the matrix. Return the k-th smallest element of the matrix. For example, consider the matrix below:

# [[ 1, 4, 7 ],
#  [ 3, 5, 9 ],
#  [ 6, 8, 11]]

# If k = 4, return 5.

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
