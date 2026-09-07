"""
Valid Sudoku [Medium]

You are given a a 9 x 9 Sudoku board. A Sudoku board is valid if the following rules are followed:
Each row must contain the digits 1-9 without duplicates.
Each column must contain the digits 1-9 without duplicates.
Each of the nine 3 x 3 sub-boxes of the grid must contain the digits 1-9 without duplicates.
Return true if the Sudoku board is valid, otherwise return false
Note: A board does not need to be full or be solvable to be valid.

Example 1:
Input: board =
[["1","2",".", ".","3",".", ".",".","."],
 ["4",".",".", "5",".",".", ".",".","."],
 [".","9","8", ".",".",".", ".",".","3"],

 ["5",".",".", ".","6",".", ".",".","4"],
 [".",".",".", "8",".","3", ".",".","5"],
 ["7",".",".", ".","2",".", ".",".","6"],

 [".",".",".", ".",".",".", "2",".","."],
 [".",".",".", "4","1","9", ".",".","8"],
 [".",".",".", ".","8",".", ".","7","9"]]
Output: true

Example 2:
Input: board =
[["1","2",".", ".","3",".", ".",".","."],
 ["4",".",".", "5",".",".", ".",".","."],
 [".","9","1", ".",".",".", ".",".","3"],

 ["5",".",".", ".","6",".", ".",".","4"],
 [".",".",".", "8",".","3", ".",".","5"],
 ["7",".",".", ".","2",".", ".",".","6"],

 [".",".",".", ".",".",".", "2",".","."],
 [".",".",".", "4","1","9", ".",".","8"],
 [".",".",".", ".","8",".", ".","7","9"]]
Output: false
Explanation: There are two 1's in the top-left 3x3 sub-box.

Constraints:
board.length == 9
board[i].length == 9
board[i][j] is a digit 1-9 or '.'.

You should aim for a solution as good or better than O(n^2) time and O(n^2) space, where n is the number of rows in the square grid.
"""


def valid_sudoku(board: list[list[str]]) -> bool:
    def get_row(i: int, board: list[list[str]]) -> list[str]:
        return [n for n in board[i] if n != "."]

    def get_col(j: int, board: list[list[str]]) -> list[str]:
        col: list[str] = []
        for row in board:
            if row[j] != ".":
                col.append(row[j])
        return col

    def get_block(bi: int, bj: int, board: list[list[str]]) -> list[str]:
        bi *= 3
        bj *= 3
        block: list[str] = []
        for i, row in enumerate(board):
            if bi <= i < bi + 3:
                for j, col in enumerate(row):
                    if bj <= j < bj + 3 and col != ".":
                        block.append(col)
        return block

    def no_duplicates(nums: list[str]) -> bool:
        return len(set(nums)) == len(nums)

    result: bool = True
    for i in range(9):
        result = result and no_duplicates(get_row(i, board))
        result = result and no_duplicates(get_col(i, board))
    for i in range(3):
        for j in range(3):
            result = result and no_duplicates(get_block(i, j, board))

    return result


def test() -> None:
    assert valid_sudoku(
        [
            ["1", "2", ".", ".", "3", ".", ".", ".", "."],
            ["4", ".", ".", "5", ".", ".", ".", ".", "."],
            [".", "9", "8", ".", ".", ".", ".", ".", "3"],
            ["5", ".", ".", ".", "6", ".", ".", ".", "4"],
            [".", ".", ".", "8", ".", "3", ".", ".", "5"],
            ["7", ".", ".", ".", "2", ".", ".", ".", "6"],
            [".", ".", ".", ".", ".", ".", "2", ".", "."],
            [".", ".", ".", "4", "1", "9", ".", ".", "8"],
            [".", ".", ".", ".", "8", ".", ".", "7", "9"],
        ]
    ), "Case 1 failed!"
    assert not valid_sudoku(
        [
            ["1", "2", ".", ".", "3", ".", ".", ".", "."],
            ["4", ".", ".", "5", ".", ".", ".", ".", "."],
            [".", "9", "1", ".", ".", ".", ".", ".", "3"],
            ["5", ".", ".", ".", "6", ".", ".", ".", "4"],
            [".", ".", ".", "8", ".", "3", ".", ".", "5"],
            ["7", ".", ".", ".", "2", ".", ".", ".", "6"],
            [".", ".", ".", ".", ".", ".", "2", ".", "."],
            [".", ".", ".", "4", "1", "9", ".", ".", "8"],
            [".", ".", ".", ".", "8", ".", ".", "7", "9"],
        ]
    ), "Case 2 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
