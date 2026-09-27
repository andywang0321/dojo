"""Serialize and Deserialize Binary Tree [Hard]

Serialization is the process of converting a data structure or object into a sequence of bits so that it can be stored in a file or memory buffer, or transmitted across a network connection link to be reconstructed later in the same or another computer environment.
Design an algorithm to serialize and deserialize a binary tree. There is no restriction on how your serialization/deserialization algorithm should work. You just need to ensure that a binary tree can be serialized to a string and this string can be deserialized to the original tree structure.
Clarification: The input/output format is the same as how LeetCode serializes a binary tree. You do not necessarily need to follow this format, so please be creative and come up with different approaches yourself.
Example 1:
Input: root = [1,2,3,null,null,4,5]
Output: [1,2,3,null,null,4,5]
Example 2:
Input: root = []
Output: []
Constraints:
* The number of nodes in the tree is in the range [0, 10^4].
* -1000 <= Node.val <= 1000

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the number of nodes in the tree.

Input format: dojo has no TreeNode and no Codec class. `serialize` receives the tree in dojo's nested-list form `[value, left, right]`, with `None` for a missing child (and `None` for an empty tree), and returns a string in whatever format you choose — the statement puts no restriction on it. `deserialize` receives that string and must return the same nested-list form. The statement's own level-order writing `[1,2,3,null,null,4,5]` is therefore `[1,[2,None,None],[3,[4,None,None],[5,None,None]]]` here, and `[]` (an empty tree) is `None`.
"""
