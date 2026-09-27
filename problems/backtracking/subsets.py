"""Subsets [Medium]

Given an integer array nums of unique elements, return all possible subsets (the power set).
The solution set must not contain duplicate subsets. Return the solution in any order.
Example 1:
Input: nums = [1,2,3]
Output: [[],[1],[2],[1,2],[3],[1,3],[2,3],[1,2,3]]
Example 2:
Input: nums = [0]
Output: [[],[0]]
Constraints:
* 1 <= nums.length <= 10
* -10 <= nums[i] <= 10
* All the numbers of nums are unique.

You should aim for a solution as good or better than O(n * 2^n) time and O(n) space, where n is the length of the nums array: the power set holds 2^n subsets and each one costs up to O(n) to copy out, and the O(n) counts the recursion depth and the subset being built rather than the answer — the returned list of subsets is not counted.
"""
