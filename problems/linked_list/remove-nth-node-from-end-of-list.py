"""Remove Nth Node From End of List [Medium]

Given the head of a linked list, remove the n^th node from the end of the list and return its head.
Example 1:
Input: head = [1,2,3,4,5], n = 2
Output: [1,2,3,5]
Example 2:
Input: head = [1], n = 1
Output: []
Example 3:
Input: head = [1,2], n = 1
Output: [1]
Constraints:
* The number of nodes in the list is sz.
* 1 <= sz <= 30
* 0 <= Node.val <= 100
* 1 <= n <= sz
Follow up: Could you do this in one pass?

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the number of nodes in the list: the intended solution finds the node with two pointers a gap of n apart in one pass over the nodes.

Input format: dojo has no ListNode, so the list arrives as a plain Python list of node values, head: list[int], where head[0] is the first node, and n is a separate int argument. The function returns the surviving values in the same form, e.g. head = [1, 2, 3, 4, 5] with n = 2 -> [1, 2, 3, 5]. Counting from the end means counting back from head[-1].
"""
