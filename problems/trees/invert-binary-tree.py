"""Invert Binary Tree [Easy]

Given the root of a binary tree, invert the tree, and return its root.
Example 1:
Input: root = [4,2,7,1,3,6,9]
Output: [4,7,2,9,6,3,1]
Example 2:
Input: root = [2,1,3]
Output: [2,3,1]
Example 3:
Input: root = []
Output: []
Constraints:
* The number of nodes in the tree is in the range [0, 100].
* -100 <= Node.val <= 100

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree.

Input format: dojo has no TreeNode — a tree arrives as a nested list [value, left, right] where left and right are either None or nested lists, and the function returns the inverted tree in that same nested-list form. An empty tree is None on both sides, so the statement's empty example comes back as None rather than []. The statement's examples are written in LeetCode's level-order array form (root = [4,2,7,1,3,6,9], null for a missing child); that array and the nested form describe the same tree, and the visible tests give both sides in the nested form.
"""
