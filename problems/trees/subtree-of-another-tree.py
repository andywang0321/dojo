"""Subtree of Another Tree [Easy]

Given the roots of two binary trees root and subRoot, return true if there is a subtree of root with the same structure and node values of subRoot and false otherwise.
A subtree of a binary tree tree is a tree that consists of a node in tree and all of this node's descendants. The tree tree could also be considered as a subtree of itself.
Example 1:
Input: root = [3,4,5,1,2], subRoot = [4,1,2]
Output: true
Example 2:
Input: root = [3,4,5,1,2,null,null,null,null,0], subRoot = [4,1,2]
Output: false
Constraints:
* The number of nodes in the root tree is in the range [1, 2000].
* The number of nodes in the subRoot tree is in the range [1, 1000].
* -10^4 <= root.val <= 10^4
* -10^4 <= subRoot.val <= 10^4

You should aim for a solution as good or better than O(n * m) time and O(n + m) space, where n and m are the numbers of nodes in root and subRoot.

Input format: dojo has no TreeNode. Both trees arrive as nested lists [value, left, right], where left and right are either None or nested lists (None is a missing child), and the function returns a plain bool. The examples in the statement write trees in LeetCode's level-order array form: [3,4,5,1,2] is the same tree as [3, [4, [1, None, None], [2, None, None]], [5, None, None]].
"""
