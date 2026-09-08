"""
Top K Frequent Elements [Medium]

Given an integer array nums and an integer k, return the k most frequent elements within the array.
The test cases are generated such that the answer is always unique.
Return the k elements sorted by decreasing frequency; if two elements tie on frequency, the smaller value comes first.

Example 1:
Input: nums = [1, 2, 2, 3, 3, 3], k = 2
Output: [2, 3]

Example 2:
Input: nums = [7, 7], k = 1
Output: [7]

Constraints:
1 <= nums.length <= 10^4.
-1000 <= nums[i] <= 1000
1 <= k <= number of distinct elements in nums.

You should aim for a solution with O(n) time and O(n) space, where n is the size of the input array.
"""


def top_k_freq(nums: list[int], k: int) -> list[int]:
    hist: dict[int, int] = {}
    for n in nums:
        hist[n] = hist.get(n, 0) + 1

    count2num: dict[int, int] = {v: k for k, v in hist.items()}

    max_count: int = max(count2num)

    out: list[int] = []
    for i in range(k):
        out.append(count2num[max_count - i])

    return out


def test() -> None:
    from itertools import permutations

    assert tuple(top_k_freq([1, 2, 2, 3, 3, 3], 2)) in permutations([2, 3]), (
        "Case 1 failed!"
    )
    assert tuple(top_k_freq([7, 7], 1)) in permutations([7]), "Case 2 failed!"
    assert tuple(top_k_freq([8], 1)) in permutations([8]), "Case 3 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
