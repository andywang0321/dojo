"""
Contains Duplicate [Easy]

Given an integer array nums, return true if any value appears more than once in the array, otherwise return false.

Example 1:
Input: nums = [1, 2, 3, 3]
Output: true

Example 2:
Input: nums = [1, 2, 3, 4]
Output: false

You should aim for a solution with O(n) time and O(n) space, where n is the size of the input array.
"""


def contains_duplicate(input: list[int]) -> bool:
    return len(input) != len(set(input))


def test() -> None:
    assert contains_duplicate([1, 2, 3, 3]), "Case 1 failed!"
    assert not contains_duplicate([1, 2, 3, 4]), "Case 2 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
