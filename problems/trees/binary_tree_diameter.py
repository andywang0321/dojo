"""
Binary Tree Diameter [Medium]

Given a binary tree, return the length of its diameter: the longest path
between any two nodes in the tree, measured in number of edges. The path may
or may not pass through the root.

Example 1:
Input: a tree whose root is 0, with left child 1 (children 2 and 2) and right
child 1 (right child 2); the left-most 2 has a right child 3 and the
right-most 2 has a left child 3.
Output: 6
Explanation: the longest path runs from one 3, up through the root, to the
other 3 — six edges.

Example 2:
Input: a single node.
Output: 0

Example 3:
Input: root 0 with left child 1, which has right child 2.
Output: 2

You should aim for a solution with O(n) time and O(n) space, where n is the
number of nodes.

Input format: the tree is passed as a nested list [value, left, right], where
left and right are either None or nested lists. The tree is never empty.
"""


class BTNode:
    def __init__(self, val):
        self.val = val
        self.left: BTNode | None = None
        self.right: BTNode | None = None


def branch_depth(root: BTNode) -> int:
    if root.left is None and root.right is None:
        return 1
    elif root.left is None:
        return branch_depth(root.right) + 1
    elif root.right is None:
        return branch_depth(root.left) + 1
    else:
        left_depth = branch_depth(root.left)
        right_depth = branch_depth(root.right)
        return max(left_depth, right_depth) + 1


def diameter(root: BTNode) -> int:
    if root.left is None and root.right is None:
        return 0
    elif root.left is None:
        return branch_depth(root.right)
    elif root.right is None:
        return branch_depth(root.left)
    else:
        return branch_depth(root.left) + branch_depth(root.right)


def main() -> None:
    A: BTNode = BTNode(0)
    A.left, A.right = BTNode(1), BTNode(1)
    A.left.left, A.left.right, A.right.right = BTNode(2), BTNode(2), BTNode(2)
    A.left.left.right, A.right.right.left = BTNode(3), BTNode(3)
    assert diameter(A) == 6, "Case 1 failed!"

    B: BTNode = BTNode(0)
    assert diameter(B) == 0, "Case 2 failed!"

    C: BTNode = BTNode(0)
    C.left = BTNode(1)
    C.left.right = BTNode(2)
    assert diameter(C) == 2, "Case 3 failed!"

    print("All tests passed!")


if __name__ == "__main__":
    main()
