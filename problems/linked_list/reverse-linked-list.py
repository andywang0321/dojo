"""Reverse Linked List [Easy]

Given the head of a singly linked list, reverse the list, and return the reversed list.
Example 1:
Input: head = [1,2,3,4,5]
Output: [5,4,3,2,1]
Example 2:
Input: head = [1,2]
Output: [2,1]
Example 3:
Input: head = []
Output: []
Constraints:
* The number of nodes in the list is the range [0, 5000].
* -5000 <= Node.val <= 5000
Follow up: A linked list can be reversed either iteratively or recursively. Could you implement both?

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the number of nodes in the list.

Input format: dojo has no ListNode, so the list arrives as a plain Python list of node values — head: list[int], where head[0] is the first node's value and head[-1] the last — and the function returns the reversed values in the same form, e.g. [1, 2, 3] -> [3, 2, 1]. An empty list means an empty list.
"""
