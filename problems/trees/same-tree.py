"""Same Tree [Easy]

Given the roots of two binary trees p and q, write a function to check if they are the same or not.
Two binary trees are considered the same if they are structurally identical, and the nodes have the same value.
Example 1:
Input: p = [1,2,3], q = [1,2,3]
Output: true
Example 2:
Input: p = [1,2], q = [1,null,2]
Output: false
Example 3:
Input: p = [1,2,1], q = [1,1,2]
Output: false
Constraints:
* The number of nodes in both trees is in the range [0, 100].
* -10^4 <= Node.val <= 10^4

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the smaller of the two trees.

Input format: dojo has no TreeNode — each tree arrives as a nested list [value, left, right] where left and right are either None or nested lists, so the function receives two such trees (p, q) and returns a bool. An empty tree is None on either side, and two empty trees are the same tree. The statement's examples are written in LeetCode's level-order array form (p = [1,2,3], q = [1,null,2], null for a missing child); that array and the nested form describe the same tree, and the visible tests give both sides in the nested form.
"""
