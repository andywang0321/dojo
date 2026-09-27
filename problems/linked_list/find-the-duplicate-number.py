"""Find the Duplicate Number [Medium]

Given an array of integers nums containing n + 1 integers where each integer is in the range [1, n] inclusive.
There is only one repeated number in nums, return this repeated number.
You must solve the problem without modifying the array nums and using only constant extra space.
Example 1:
Input: nums = [1,3,4,2,2]
Output: 2
Example 2:
Input: nums = [3,1,3,4,2]
Output: 3
Example 3:
Input: nums = [3,3,3,3,3]
Output: 3
Constraints:
* 1 <= n <= 10^5
* nums.length == n + 1
* 1 <= nums[i] <= n
* All the integers in nums appear only once except for precisely one integer which appears two or more times.
Follow up:
* How can we prove that at least one duplicate number must exist in nums?
* Can you solve the problem in linear runtime complexity?

Group note: this one is an array in the roadmap's linked-list group. The intended solution reads nums as a linked list — index i points at index nums[i], the repeated value is where that walk enters its cycle — so it is Floyd's two-pointer algorithm from the linked-list group applied to values instead of nodes. There is no representation change: the function takes nums exactly as the statement writes it and returns the repeated number.

Group note: this one is an array in the roadmap's linked-list group. The intended solution reads nums as a linked list — index i points at index nums[i], the repeated value is where that walk enters its cycle — so it is Floyd's two-pointer algorithm from the linked-list group applied to values instead of nodes. There is no representation change: the function takes nums exactly as the statement writes it and returns the repeated number.

Group note: this one is an array in the roadmap's linked-list group. The intended solution reads nums as a linked list — index i points at index nums[i], the repeated value is where that walk enters its cycle — so it is Floyd's two-pointer algorithm from the linked-list group applied to values instead of nodes. There is no representation change: the function takes nums exactly as the statement writes it and returns the repeated number.

Group note (there is no representation change here): this one is an array in the roadmap's linked-list group. The intended solution reads nums as a linked list — index i points at index nums[i], the repeated value is where that walk enters its cycle — so it is Floyd's two-pointer algorithm from the linked-list group applied to values instead of nodes. There is no representation change: the function takes nums exactly as the statement writes it and returns the repeated number.

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the length of the nums array minus one (the array holds n + 1 integers in the range [1, n]).

Group note (there is no representation change here): this one is an array in the roadmap's linked-list group. The intended solution reads nums as a linked list — index i points at index nums[i], the repeated value is where that walk enters its cycle — so it is Floyd's two-pointer algorithm from the linked-list group applied to values instead of nodes. There is no representation change: the function takes nums exactly as the statement writes it and returns the repeated number.
"""
