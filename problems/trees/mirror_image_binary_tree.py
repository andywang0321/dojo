"""
Symmetric Binary Tree [Easy]

Given a binary tree, return true if the tree is a mirror image of itself. A
tree is symmetric when its left and right subtrees are mirror images of each
other: their root values are equal, and the left subtree of one mirrors the
right subtree of the other (and vice versa).

Example 1: a tree whose root is 3, whose left child 2 has children 1 and 2,
and whose right child 2 has children 2 and 1, is symmetric -> true.

Example 2: a tree whose root is 3, whose left child 2 has children 1 and 2,
and whose right child 4 has children 1 and 1, is not symmetric -> false.

You should aim for a solution with O(n) time and O(n) space, where n is the
number of nodes.

Input format: the tree is passed as a nested list [value, left, right], where
left and right are either None or nested lists. An empty tree is None.
"""

class BTNode:
    def __init__(self, val):
        self.val = val
        self.left: BTNode | None = None
        self.right: BTNode | None = None

def check_mirror(left: BTNode | None, right: BTNode | None) -> bool:
    if left is None and right is None:
        return True
    elif left is None or right is None:
        return False
    return (
        check_mirror(left.left, right.right)
        and check_mirror(right.left, left.right)
        and (left.val == right.val)
    )

def is_mirror(root: BTNode | None) -> bool:
    if root is None:
        return True
    return check_mirror(root.left, root.right)

def main() -> None:
    mirror = BTNode(3)
    mirror.left, mirror.right = BTNode(2), BTNode(2)
    mirror.left.left, mirror.left.right, mirror.right.left, mirror.right.right = BTNode(1), BTNode(2), BTNode(2), BTNode(1)

    assert is_mirror(mirror), "Mirror case failed!"

    tree = BTNode(3)
    tree.left, tree.right = BTNode(2), BTNode(4)
    tree.left.left, tree.left.right, tree.right.left, tree.right.right = BTNode(1), BTNode(2), BTNode(1), BTNode(1)

    assert not is_mirror(tree), "Non-mirror case failed!"

    print("All tests passed!")

if __name__ == "__main__":
    main()
