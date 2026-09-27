"""Kth Largest Element in an Array [Medium]

Given an integer array nums and an integer k, return the k^th largest element in the array.
Note that it is the k^th largest element in the sorted order, not the k^th distinct element.
Can you solve it without sorting?
Example 1:
Input: nums = [3,2,1,5,6,4], k = 2
Output: 5
Example 2:
Input: nums = [3,2,3,1,2,4,5,5,6], k = 4
Output: 4
Constraints:
* 1 <= k <= nums.length <= 10^5
* -10^4 <= nums[i] <= 10^4

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the length of the nums array: quickselect partitions in place and is O(n) on average (its worst case is O(n^2)), while a size-k min-heap reaches O(n log k) time and O(k) space and is equally accepted.
"""
