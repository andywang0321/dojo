"""Binary Tree Right Side View [Medium]

Given the root of a binary tree, imagine yourself standing on the right side of it, return the values of the nodes you can see ordered from top to bottom.
Example 1:
Input: root = [1,2,3,null,5,null,4]
Output: [1,3,4]
Explanation:
Example 2:
Input: root = [1,2,3,4,null,null,null,5]
Output: [1,3,4,5]
Explanation:
Example 3:
Input: root = [1,null,3]
Output: [1,3]
Example 4:
Input: root = []
Output: []
Constraints:
* The number of nodes in the tree is in the range [0, 100].
* -100 <= Node.val <= 100

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree.

Input format: dojo has no TreeNode. The tree arrives as a nested list [value, left, right], where left and right are either None or nested lists; None is a missing child and the empty tree is None. The function returns the visible values as a plain list of integers, top to bottom. The examples above write the tree in LeetCode's level-order array form: [1,2,3,null,5,null,4] is the same tree as [1, [2, None, [5, None, None]], [3, None, [4, None, None]]].
"""
