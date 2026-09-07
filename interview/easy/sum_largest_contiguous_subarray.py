# Akuna Capital: Given an integer array, find the sum of the largest contiguous subarray within the array.

# For example, if the input is [ -1, -3, 5, -4, 3, -6, 9, 2 ], then return 11 (because [9, 2]).
# Note that if all the elements are negative, you should return 0.


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
