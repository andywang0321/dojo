"""Surrounded Regions [Medium]

You are given an m x n matrix board containing letters 'X' and 'O', capture regions that are surrounded:
* Connect: A cell is connected to adjacent cells horizontally or vertically.
* Region: To form a region connect every 'O' cell.
* Surround: A region is surrounded if none of the 'O' cells in that region are on the edge of the board. Such regions are completely enclosed by 'X' cells.
To capture a surrounded region, replace all 'O's with 'X's in-place within the original board. You do not need to return anything.
Example 1:
Input: board = [["X","X","X","X"],["X","O","O","X"],["X","X","O","X"],["X","O","X","X"]]
Output: [["X","X","X","X"],["X","X","X","X"],["X","X","X","X"],["X","O","X","X"]]
Explanation:
In the above diagram, the bottom region is not captured because it is on the edge of the board and cannot be surrounded.
Example 2:
Input: board = [["X"]]
Output: [["X"]]
Constraints:
* m == board.length
* n == board[i].length
* 1 <= m, n <= 200
* board[i][j] is 'X' or 'O'.

You should aim for a solution as good or better than O(m * n) time and O(m * n) space, where m and n are the number of rows and columns of the board.

Input format: dojo passes the board as a plain list of lists of strings — board: list[list[str]] — and grades the capture by the state of THAT board after the call, not by a returned value: the function returns nothing (None), and a solution that builds a new board and rebinds the name (or returns it) leaves everything the judge can see unchanged, so it fails. Every cell is 'X' or 'O' on input and on output; the minimal enclosed region, [["X","X","X"],["X","O","X"],["X","X","X"]], must come back all 'X'.
"""
