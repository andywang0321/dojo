"""Permutations [Medium]

Given an array nums of distinct integers, return all the possible permutations. You can return the answer in any order.
Example 1:
Input: nums = [1,2,3]
Output: [[1,2,3],[1,3,2],[2,1,3],[2,3,1],[3,1,2],[3,2,1]]
Example 2:
Input: nums = [0,1]
Output: [[0,1],[1,0]]
Example 3:
Input: nums = [1]
Output: [[1]]
Constraints:
* 1 <= nums.length <= 6
* -10 <= nums[i] <= 10
* All the integers of nums are unique.

You should aim for a solution as good or better than O(n * n!) time and O(n) space, where n is the length of the nums array: there are n! arrangements and each one costs O(n) to copy out, and the O(n) is the recursion depth plus the bookkeeping of which values are already used — the returned list of permutations is not counted.
"""
