"""Unique Paths [Medium]

There is a robot on an m x n grid. The robot is initially located at the top-left corner (i.e., grid[0][0]). The robot tries to move to the bottom-right corner (i.e., grid[m - 1][n - 1]). The robot can only move either down or right at any point in time.
Given the two integers m and n, return the number of possible unique paths that the robot can take to reach the bottom-right corner.
The test cases are generated so that the answer will be less than or equal to 2 * 10^9.
Example 1:
Input: m = 3, n = 7
Output: 28
Example 2:
Input: m = 3, n = 2
Output: 3
Explanation: From the top-left corner, there are a total of 3 ways to reach the bottom-right corner:
1. Right -> Down -> Down
2. Down -> Down -> Right
3. Down -> Right -> Down
Constraints:
* 1 <= m, n <= 100

You should aim for a solution as good or better than O(m * n) time and O(min(m, n)) space, where m and n are the number of rows and columns of the grid: every one of the m * n cells is settled once from the cell above it and the cell to its left, and rolling a single row over the shorter dimension is the smallest workspace that recurrence needs.
"""
