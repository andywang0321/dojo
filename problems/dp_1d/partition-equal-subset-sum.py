"""Partition Equal Subset Sum [Medium]

Given an integer array nums, return true if you can partition the array into two subsets such that the sum of the elements in both subsets is equal or false otherwise.
Example 1:
Input: nums = [1,5,11,5]
Output: true
Explanation: The array can be partitioned as [1, 5, 5] and [11].
Example 2:
Input: nums = [1,2,3,5]
Output: false
Explanation: The array cannot be partitioned into equal sum subsets.
Constraints:
* 1 <= nums.length <= 200
* 1 <= nums[i] <= 100

You should aim for a solution as good or better than O(n^2) time and O(n) space, where n is the length of nums: the target is half of the total sum, which the statement's own value bound (1 <= nums[i] <= 100) caps at 50 * n, so the intended one-dimensional DP over reachable sums costs n * target = O(n^2) time and keeps one array of that many flags.
"""
