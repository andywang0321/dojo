"""
Merge Sort Implementation
"""


def merge(left: list[int], right: list[int]) -> list[int]:
    result: list[int] = []
    i, j = 0, 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result += left[i:]
    result += right[j:]
    return result


def mergesort(arr: list[int]) -> list[int]:
    if len(arr) < 2:
        return arr
    middle = len(arr) // 2
    left = mergesort(arr[:middle])
    right = mergesort(arr[middle:])
    return merge(left, right)


if __name__ == "__main__":
    A = [3, 5, 1, 6, 9, 3, 0, 33]
    assert mergesort(A) == sorted(A), "Merge Sort failed!"
    B = [1]
    assert mergesort(B) == [1], "Merge Sort failed!"
    print("All tests passed!")
