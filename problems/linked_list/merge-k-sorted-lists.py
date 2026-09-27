"""Merge k Sorted Lists [Hard]

You are given an array of k linked-lists lists, each linked-list is sorted in ascending order.
Merge all the linked-lists into one sorted linked-list and return it.
Example 1:
Input: lists = [[1,4,5],[1,3,4],[2,6]]
Output: [1,1,2,3,4,4,5,6]
Explanation: The linked-lists are:
[
  1->4->5,
  1->3->4,
  2->6
]
merging them into one sorted linked list:
1->1->2->3->4->4->5->6
Example 2:
Input: lists = []
Output: []
Example 3:
Input: lists = [[]]
Output: []
Constraints:
* k == lists.length
* 0 <= k <= 10^4
* 0 <= lists[i].length <= 500
* -10^4 <= lists[i][j] <= 10^4
* lists[i] is sorted in ascending order.
* The sum of lists[i].length will not exceed 10^4.

You should aim for a solution as good or better than O(n log n) time and O(n) space, where n is the total number of nodes across all the lists: the intended k-way merge keeps one heap entry per list, which is O(n log k) time and O(k) extra space with k the number of lists — inside both bounds, since k <= n.

Input format: dojo has no ListNode, so lists arrives as a plain Python list of value lists — lists[i] is the values of the i-th linked list, head first, each list sorted in ascending order, and any of them possibly empty — and the function returns the merged values in the same form, e.g. [[1, 4, 5], [1, 3, 4], [2, 6]] -> [1, 1, 2, 3, 4, 4, 5, 6]. Splicing nodes together means the merged sequence keeps every list's order, which for sorted lists is the sorted merge of their values.
"""
