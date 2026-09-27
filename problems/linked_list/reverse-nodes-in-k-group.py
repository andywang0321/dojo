"""Reverse Nodes in k-Group [Hard]

Given the head of a linked list, reverse the nodes of the list k at a time, and return the modified list.
k is a positive integer and is less than or equal to the length of the linked list. If the number of nodes is not a multiple of k then left-out nodes, in the end, should remain as it is.
You may not alter the values in the list's nodes, only nodes themselves may be changed.
Example 1:
Input: head = [1,2,3,4,5], k = 2
Output: [2,1,4,3,5]
Example 2:
Input: head = [1,2,3,4,5], k = 3
Output: [3,2,1,4,5]
Constraints:
* The number of nodes in the list is n.
* 1 <= k <= n <= 5000
* 0 <= Node.val <= 1000
Follow-up: Can you solve the problem in O(1) extra memory space?

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the number of nodes in the list: the follow-up's O(1) extra memory means reversing the blocks in place rather than copying the list.

Input format: dojo has no ListNode, so head arrives as a plain Python list of node values — head[0] is the first node's value, head[-1] the last — and the function returns the reordered values in the same form, e.g. [1, 2, 3, 4, 5] with k = 2 -> [2, 1, 4, 3, 5]. Relinking nodes and reordering values are the same operation on this representation, so the statement's "you may not alter the values in the list's nodes" rule is graded as the order of the values you return: leave the leftover nodes' values where they are and reverse each complete group of k by position.
"""
