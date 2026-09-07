# Amazon: Given a binary tree, write a function to determine the diameter of the tree, which is the longest path between any two nodes.


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
