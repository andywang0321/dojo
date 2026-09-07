"""
Products of Array Except Self [Medium]

Given an integer array nums, return an array output where output[i] is the product of all the elements of nums except nums[i].
Each product is guaranteed to fit in a 32-bit integer.

Follow-up: Could you solve it in O(n) time without using the division operation?

Example 1:
Input: nums = [1,2,4,6]
Output: [48,24,12,8]

Example 2:
Input: nums = [-1,0,1,2,3]
Output: [0,-6,0,0,0]

Constraints:
2 <= nums.length <= 1000
-20 <= nums[i] <= 20

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the size of the input array.
"""


def prod_except_self(nums: list[int]) -> list[int]:
    if nums == []:
        return []

    def cumprod(nums: list[int]) -> list[int]:
        out: list[int] = [nums[0]]
        for n in nums[1:]:
            out.append(out[-1] * n)
        return out

    cp: list[int] = [1] + cumprod(nums)
    rcp: list[int] = cumprod(nums[::-1])[::-1] + [1]

    return [x * y for x, y in zip(cp[:-1], rcp[1:])]


def test() -> None:
    assert prod_except_self([1, 2, 4, 6]) == [48, 24, 12, 8], "Case 1 failed!"
    assert prod_except_self([-1, 0, 1, 2, 3]) == [0, -6, 0, 0, 0], "Case 2 failed!"
    assert prod_except_self([]) == [], "Case 3 failed!"
    assert prod_except_self([1, 0, 2, 0, 3, 4]) == [0, 0, 0, 0, 0, 0], "Case 4 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
