"""
Graph Valid Tree [Medium]

You are given n nodes labelled 0 to n - 1 and a list of undirected edges where edges[i] = [a_i, b_i] connects node a_i and node b_i. Return true if these edges form a valid tree.

A graph is a valid tree when it is connected and acyclic: every node is reachable from every other node, and there is exactly one path between any two nodes.

Example 1:
Input: n = 5, edges = [[0,1],[0,2],[0,3],[1,4]]
Output: true
Explanation: all five nodes are connected and no cycle exists.

Example 2:
Input: n = 5, edges = [[0,1],[1,2],[2,3],[1,3],[1,4]]
Output: false
Explanation: nodes 1, 2 and 3 form a cycle.

Example 3:
Input: n = 4, edges = [[0,1],[2,3]]
Output: false
Explanation: the graph is acyclic but not connected.

Constraints:
* 1 <= n <= 2000
* 0 <= edges.length <= 5000
* edges[i].length == 2
* 0 <= a_i, b_i <= n - 1
* a_i != b_i
* There are no self-loops and no repeated edges.

You should aim for a solution as good or better than O(n + e) time and O(n) space, where n is the number of nodes and e is the number of edges: every edge has to be looked at once, and a union-find settles the whole question with one parent array over the n nodes (a traversal that builds an adjacency list uses O(n + e) space instead).
"""
