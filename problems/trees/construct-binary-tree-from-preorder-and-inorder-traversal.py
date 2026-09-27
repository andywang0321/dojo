"""Construct Binary Tree from Preorder and Inorder Traversal [Medium]

Given two integer arrays preorder and inorder where preorder is the preorder traversal of a binary tree and inorder is the inorder traversal of the same tree, construct and return the binary tree.
Example 1:
Input: preorder = [3,9,20,15,7], inorder = [9,3,15,20,7]
Output: [3,9,20,null,null,15,7]
Example 2:
Input: preorder = [-1], inorder = [-1]
Output: [-1]
Constraints:
* 1 <= preorder.length <= 3000
* inorder.length == preorder.length
* -3000 <= preorder[i], inorder[i] <= 3000
* preorder and inorder consist of unique values.
* Each value of inorder also appears in preorder.
* preorder is guaranteed to be the preorder traversal of the tree.
* inorder is guaranteed to be the inorder traversal of the tree.

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree.

Input format: dojo has no TreeNode. The two traversals arrive as plain lists of ints — `preorder: list[int]`, `inorder: list[int]` — and the tree must be returned in dojo's nested-list form `[value, left, right]`, with `None` for a missing child (and `None` for an empty tree). That is not a LeetCode level-order array: the statement's Example 1 output `[3,9,20,null,null,15,7]` is the level-order writing of the tree this form spells `[3,[9,None,None],[20,[15,None,None],[7,None,None]]]`.
"""
