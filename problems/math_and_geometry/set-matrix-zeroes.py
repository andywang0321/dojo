"""Set Matrix Zeroes [Medium]

Given an m x n integer matrix matrix, if an element is 0, set its entire row and column to 0's.
You must do it in place.
Example 1:
Input: matrix = [[1,1,1],[1,0,1],[1,1,1]]
Output: [[1,0,1],[0,0,0],[1,0,1]]
Example 2:
Input: matrix = [[0,1,2,0],[3,4,5,2],[1,3,1,5]]
Output: [[0,0,0,0],[0,4,5,0],[0,3,1,0]]
Constraints:
* m == matrix.length
* n == matrix[0].length
* 1 <= m, n <= 200
* -2^31 <= matrix[i][j] <= 2^31 - 1
Follow up:
* A straightforward solution using O(mn) space is probably a bad idea.
* A simple improvement uses O(m + n) space, but still not the best solution.
* Could you devise a constant space solution?

You should aim for a solution as good or better than O(m * n) time and O(1) space, where m and n are the number of rows and columns of the matrix: the follow-up's constant-space marking keeps its flags in the matrix's own first row and column instead of in a second structure.

Input format: dojo passes the matrix as a plain list of lists of ints — matrix: list[list[int]] — and grades the zeroing by the state of THAT matrix after the call, not by a returned value: the function returns nothing (None), and a solution that builds a new matrix and rebinds the name (or returns it) leaves everything the judge can see unchanged, so it fails. Set [[1, 0], [2, 3]] by writing into that same matrix to get [[0, 0], [2, 0]].
"""
