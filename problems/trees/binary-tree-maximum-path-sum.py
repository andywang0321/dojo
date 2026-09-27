"""Binary Tree Maximum Path Sum [Hard]

A path in a binary tree is a sequence of nodes where each pair of adjacent nodes in the sequence has an edge connecting them. A node can only appear in the sequence at most once. Note that the path does not need to pass through the root.
The path sum of a path is the sum of the node's values in the path.
Given the root of a binary tree, return the maximum path sum of any non-empty path.
Example 1:
Input: root = [1,2,3]
Output: 6
Explanation: The optimal path is 2 -> 1 -> 3 with a path sum of 2 + 1 + 3 = 6.
Example 2:
Input: root = [-10,9,20,null,null,15,7]
Output: 42
Explanation: The optimal path is 15 -> 20 -> 7 with a path sum of 15 + 20 + 7 = 42.
Constraints:
* The number of nodes in the tree is in the range [1, 3 * 10^4].
* -1000 <= Node.val <= 1000

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree.

Input format: dojo has no TreeNode. `root` arrives in dojo's nested-list form `[value, left, right]`, with `None` for a missing child (and `None` for an empty tree) — the same form the function returns, since the answer is a sum. The statement's Example 1 `root = [1,2,3]` is therefore `[1,[2,None,None],[3,None,None]]` and Example 2's `[-10,9,20,null,null,15,7]` is `[-10,[9,None,None],[20,[15,None,None],[7,None,None]]]`.
"""
