"""Balanced Binary Tree [Easy]

Given a binary tree, determine if it is height-balanced.
Example 1:
Input: root = [3,9,20,null,null,15,7]
Output: true
Example 2:
Input: root = [1,2,2,3,3,null,null,4,4]
Output: false
Example 3:
Input: root = []
Output: true
Constraints:
* The number of nodes in the tree is in the range [0, 5000].
* -10^4 <= Node.val <= 10^4

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree.

Input format: dojo has no TreeNode — the tree arrives as a nested list [value, left, right] where left and right are either None or nested lists, and the function returns a bool. An empty tree is None and is height-balanced (true). The statement's examples are written in LeetCode's level-order array form (root = [3,9,20,null,null,15,7], null for a missing child); that array and the nested form describe the same tree, and the visible tests give the input in the nested form. Height-balanced means: at every node, the heights of the two subtrees differ by at most one.
"""
