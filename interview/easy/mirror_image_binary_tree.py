# Facebook: Given a binary tree, write a function to determine whether the tree is a mirror image of itself.
# Two trees are a mirror image of each other if their root values are the same and the left subtree is a mirror image of the right subtree.

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
