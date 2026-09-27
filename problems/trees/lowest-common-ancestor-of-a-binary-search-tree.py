"""Lowest Common Ancestor of a Binary Search Tree [Medium]

Given a binary search tree (BST), find the lowest common ancestor (LCA) node of two given nodes in the BST.
According to the definition of LCA on Wikipedia: “The lowest common ancestor is defined between two nodes p and q as the lowest node in T that has both p and q as descendants (where we allow a node to be a descendant of itself).”
Example 1:
Input: root = [6,2,8,0,4,7,9,null,null,3,5], p = 2, q = 8
Output: 6
Explanation: The LCA of nodes 2 and 8 is 6.
Example 2:
Input: root = [6,2,8,0,4,7,9,null,null,3,5], p = 2, q = 4
Output: 2
Explanation: The LCA of nodes 2 and 4 is 2, since a node can be a descendant of itself according to the LCA definition.
Example 3:
Input: root = [2,1], p = 2, q = 1
Output: 2
Constraints:
* The number of nodes in the tree is in the range [2, 10^5].
* -10^9 <= Node.val <= 10^9
* All Node.val are unique.
* p != q
* p and q will exist in the BST.

You should aim for a solution as good or better than O(h) time and O(1) space, where h is the height of the BST (O(log n) when the tree is balanced, O(n) in the worst case).

Input format: dojo has no TreeNode. The BST arrives as a nested list [value, left, right], where left and right are either None or nested lists (None is a missing child). p and q arrive as the two nodes' integer *values* (the statement guarantees all values are unique, so a value names exactly one node), and the function returns the value of the lowest common ancestor node -- not the node, and not its subtree. The examples above write the tree in LeetCode's level-order array form: [6,2,8,0,4,7,9,null,null,3,5] is the same tree as [6, [2, [0, None, None], [4, [3, None, None], [5, None, None]]], [8, [7, None, None], [9, None, None]]].
"""
