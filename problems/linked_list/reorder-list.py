"""Reorder List [Medium]

You are given the head of a singly linked-list. The list can be represented as:
L0 → L1 → … → Ln - 1 → Ln
Reorder the list to be on the following form:
L0 → Ln → L1 → Ln - 1 → L2 → Ln - 2 → …
You may not modify the values in the list's nodes. Only nodes themselves may be changed.
Example 1:
Input: head = [1,2,3,4]
Output: [1,4,2,3]
Example 2:
Input: head = [1,2,3,4,5]
Output: [1,5,2,4,3]
Constraints:
* The number of nodes in the list is in the range [1, 5 * 10^4].
* 1 <= Node.val <= 1000

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the list: the intended solution reverses the second half in place and then interleaves the two halves, and over a Python list that interleave needs one temporary list of n values.

Input format: dojo has no ListNode, so the list arrives as a plain Python list of node values — head: list[int], where head[0] is L0 and head[-1] is Ln — and the reorder must happen IN PLACE in that list: dojo grades the argument list as it stands after the call, not the return value, so the function returns nothing (None) and a solution that builds a new list and rebinds the name changes nothing the judge can see. Reorder [1, 2, 3, 4] by writing into that same list to get [1, 4, 2, 3].
"""
