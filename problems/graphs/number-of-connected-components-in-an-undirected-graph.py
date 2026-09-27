"""
Number of Connected Components in an Undirected Graph [Medium]

You have a graph of n nodes labelled 0 to n - 1. You are given the integer n and a list of undirected edges where edges[i] = [a_i, b_i] connects node a_i and node b_i. Return the number of connected components in the graph.

Example 1:
Input: n = 5, edges = [[0,1],[1,2],[3,4]]
Output: 2
Explanation: nodes 0, 1 and 2 form one component and nodes 3 and 4 form another.

Example 2:
Input: n = 5, edges = [[0,1],[1,2],[2,3],[3,4]]
Output: 1
Explanation: every node is reachable from every other node.

Example 3:
Input: n = 3, edges = []
Output: 3
Explanation: with no edges each node is its own component.

Constraints:
* 1 <= n <= 2000
* 0 <= edges.length <= 5000
* edges[i].length == 2
* 0 <= a_i, b_i <= n - 1
* a_i != b_i
* There are no repeated edges.

You should aim for a solution as good or better than O(n + e) time and O(n) space, where n is the number of nodes and e is the number of edges: each edge can only ever merge two components, so one pass over the edges with a parent array over the n nodes is enough, and the graph never has to be rebuilt as an adjacency list.
"""
