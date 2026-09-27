"""Binary Tree Level Order Traversal [Medium]

Given the root of a binary tree, return the level order traversal of its nodes' values. (i.e., from left to right, level by level).
Example 1:
Input: root = [3,9,20,null,null,15,7]
Output: [[3],[9,20],[15,7]]
Example 2:
Input: root = [1]
Output: [[1]]
Example 3:
Input: root = []
Output: []
Constraints:
* The number of nodes in the tree is in the range [0, 2000].
* -1000 <= Node.val <= 1000

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree (the output itself holds n values, which is why the space target is not O(1)).

Input format: dojo has no TreeNode. The tree arrives as a nested list [value, left, right], where left and right are either None or nested lists; None is a missing child and the empty tree is None. The function returns the levels as a plain list of lists of integers, exactly as the examples show. The examples above write the tree in LeetCode's level-order array form: [3,9,20,null,null,15,7] is the same tree as [3, [9, None, None], [20, [15, None, None], [7, None, None]]].
"""
