"""
Two Sum [Easy]

Given an array of integers nums and an integer target, return the indices i and j such that nums[i] + nums[j] == target and i != j.
You may assume that every input has exactly one pair of indices i and j that satisfy the condition.
Return the answer with the smaller index first.

Example 1:
Input: nums = [3,4,5,6], target = 7
Output: [0,1]
Explanation: nums[0] + nums[1] == 7, so we return [0, 1].

Example 2:
Input: nums = [4,5,6], target = 10
Output: [0,2]

Example 3:
Input: nums = [5,5], target = 10
Output: [0,1]

Constraints:
2 <= nums.length <= 1000
-10,000,000 <= nums[i] <= 10,000,000
-10,000,000 <= target <= 10,000,000

You should aim for a solution with O(n) time and O(n) space, where n is the size of the input array.
"""


# def twosum(nums: list[int], target: int) -> list[int]:
#     num_set: set[int] = set(nums)
#     for i, num in enumerate(nums):
#         diff: int = target - num
#         if diff in num_set:
#             for j, other_num in enumerate(nums[i + 1:]):
#                 if other_num == diff:
#                     return [i, i + 1 + j]
#     return []


def twosum(nums: list[int], target: int) -> list[int]:
    num2ind: dict = {}
    for i, num in enumerate(nums):
        diff: int = target - num
        if diff in num2ind:
            return [num2ind[diff], i]
        num2ind[num] = i
    return []


def test() -> None:
    assert twosum([3, 4, 5, 6], 7) == [0, 1], "Case 1 failed!"
    assert twosum([4, 5, 6], 10) == [0, 2], "Case 2 failed!"
    assert twosum([5, 5], 10) == [0, 1], "Case 3 failed!"
    assert twosum([1, 2, 5, 5], 10) == [2, 3], "Case 4 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
