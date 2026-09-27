"""Merge Two Sorted Lists [Easy]

You are given the heads of two sorted linked lists list1 and list2.
Merge the two lists into one sorted list. The list should be made by splicing together the nodes of the first two lists.
Return the head of the merged linked list.
Example 1:
Input: list1 = [1,2,4], list2 = [1,3,4]
Output: [1,1,2,3,4,4]
Example 2:
Input: list1 = [], list2 = []
Output: []
Example 3:
Input: list1 = [], list2 = [0]
Output: [0]
Constraints:
* The number of nodes in both lists is in the range [0, 50].
* -100 <= Node.val <= 100
* Both list1 and list2 are sorted in non-decreasing order.

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the total number of nodes in the two lists: the intended merge walks each node once and keeps nothing beyond the merged list it returns.

Input format: dojo has no ListNode, so each list arrives as a plain Python list of node values — list1: list[int] and list2: list[int], each sorted in non-decreasing order and possibly empty — and the function returns the merged values in the same form, e.g. [1, 2, 4] and [1, 3, 4] -> [1, 1, 2, 3, 4, 4]. Splicing the nodes together means the merged sequence keeps each list's order, which for two sorted lists is the sorted merge of their values.
"""
