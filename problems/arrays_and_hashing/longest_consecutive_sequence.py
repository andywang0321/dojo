"""
Longest Consecutive Sequence [Medium]

Given an array of integers nums, return the length of the longest consecutive sequence of elements that can be formed.
A consecutive sequence is a sequence of elements in which each element is exactly 1 greater than the previous element.
The elements do not have to be consecutive in the original array.
You must write an algorithm that runs in O(n) time.

Example 1:
Input: nums = [2, 20, 4, 10, 3, 4, 5]
Output: 4
Explanation: The longest consecutive sequence is [2, 3, 4, 5].

Example 2:
Input: nums = [0, 3, 2, 5, 4, 6, 1, 1]
Output: 7

Constraints:
0 <= nums.length <= 1000
-10^9 <= nums[i] <= 10^9

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the size of the input array.
"""


def longest_seqlen(nums: list[int]) -> int:
    num_set: set[int] = set(nums)
    longest: int = 0
    for num in nums:
        if num - 1 not in num_set:
            seqlen: int = 1
            while num + seqlen in num_set:
                seqlen += 1
            longest = max(longest, seqlen)
    return longest


# def longest_seqlen(nums: list[int]) -> int:
#     num_set: set[int] = set(nums)
#     seq_starts: list[int] = []
#     for num in nums:
#         if num - 1 not in num_set:
#             seq_starts.append(num)
#     cur_longest_seqlen: int = 0
#     for num in seq_starts:
#         seqlen: int = 1
#         while num + 1 in num_set:
#             num += 1
#             seqlen += 1
#         cur_longest_seqlen = max(seqlen, cur_longest_seqlen)
#     return cur_longest_seqlen


def test() -> None:
    assert longest_seqlen([2, 20, 4, 10, 3, 4, 5]) == 4, "Case 1 failed!"
    assert longest_seqlen([0, 3, 2, 5, 4, 6, 1, 1]) == 7, "Case 2 failed!"
    assert longest_seqlen([10, 9, 8, 1, 2, 3, 12, 4, 11, 13]) == 6, "Case 3 failed!"
    assert longest_seqlen([]) == 0, "Case 4 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
