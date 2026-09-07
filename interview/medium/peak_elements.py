# Google: Given an array of positive integers, a peak element is greater than its neighbors. Write a function to find the index of any peak elements.

# For example, for [3, 5, 2, 4, 1], you should return either 1 or 3 because the values at those indices, 5 and 4, are both peak elements.


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
