"""Subsets II [Medium]

Given an integer array nums that may contain duplicates, return all possible subsets (the power set).
The solution set must not contain duplicate subsets. Return the solution in any order.
Example 1:
Input: nums = [1,2,2]
Output: [[],[1],[1,2],[1,2,2],[2],[2,2]]
Example 2:
Input: nums = [0]
Output: [[],[0]]
Constraints:
* 1 <= nums.length <= 10
* -10 <= nums[i] <= 10

You should aim for a solution as good or better than O(n * 2^n) time and O(n) space, where n is the length of nums -- the power set holds at most 2^n subsets and each one costs up to n to copy into the answer, so the output itself sets the floor; sorting first and skipping a repeated value at the level of the search where another copy already built that branch is what keeps every distinct subset in the answer exactly once.
"""
