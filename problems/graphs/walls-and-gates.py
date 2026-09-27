"""
Walls and Gates [Medium]

You are given an m x n grid rooms whose cells hold one of three values:

* -1 is a wall or an obstacle.
* 0 is a gate.
* 2147483647 (INF) is an empty room.

Fill every empty room with the distance to its nearest gate, moving only up, down, left and right. An empty room that cannot reach any gate stays INF.

Modify the grid in place and return nothing.

Example 1:
Input: rooms = [[2147483647,-1,0,2147483647],[2147483647,2147483647,2147483647,-1],[2147483647,-1,2147483647,-1],[0,-1,2147483647,2147483647]]
Output: [[3,-1,0,1],[2,2,1,-1],[1,-1,2,-1],[0,-1,3,4]]
Explanation: the two gates fill their reachable rooms, and the rooms that no gate can reach keep INF.

Example 2:
Input: rooms = [[-1]]
Output: [[-1]]
Explanation: a single wall — nothing to fill.

Constraints:
* m == rooms.length
* n == rooms[i].length
* 1 <= m, n <= 250
* rooms[i][j] is -1, 0, or 2147483647.

You should aim for a solution as good or better than O(m * n) time and O(m * n) space, where m is the number of rows and n is the number of columns.

Representation: rooms arrives as list[list[int]] -- an integer grid is already dojo's own shape -- and dojo grades the grid as it stands after the call, so the return value is ignored: mutate rooms in place and return nothing.
"""
