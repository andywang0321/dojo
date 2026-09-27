"""Maximum Product Subarray [Medium]

Given an integer array nums, find a subarray that has the largest product, and return the product.
The test cases are generated so that the answer will fit in a 32-bit integer.
Note that the product of an array with a single element is the value of that element.
Example 1:
Input: nums = [2,3,-2,4]
Output: 6
Explanation: [2,3] has the largest product 6.
Example 2:
Input: nums = [-2,0,-1]
Output: 0
Explanation: The result cannot be 2, because [-2,-1] is not a subarray.
Constraints:
* 1 <= nums.length <= 2 * 10^4
* -10 <= nums[i] <= 10
* The product of any subarray of nums is guaranteed to fit in a 32-bit integer.

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the length of the nums array: the intended single pass carries the largest and smallest product of a subarray ending at each position -- a negative value swaps their roles, and a zero resets both -- so a pair of negatives is carried through the smallest side instead of being dropped.
"""
