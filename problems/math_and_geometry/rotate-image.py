"""Rotate Image [Medium]

You are given an n x n 2D matrix representing an image, rotate the image by 90 degrees (clockwise).
You have to rotate the image in-place, which means you have to modify the input 2D matrix directly. DO NOT allocate another 2D matrix and do the rotation.
Example 1:
Input: matrix = [[1,2,3],[4,5,6],[7,8,9]]
Output: [[7,4,1],[8,5,2],[9,6,3]]
Example 2:
Input: matrix = [[5,1,9,11],[2,4,8,10],[13,3,6,7],[15,14,12,16]]
Output: [[15,13,2,5],[14,3,4,1],[12,6,8,9],[16,7,10,11]]
Constraints:
* n == matrix.length == matrix[i].length
* 1 <= n <= 20
* -1000 <= matrix[i][j] <= 1000

You should aim for a solution as good or better than O(n^2) time and O(1) space, where n is the side length of the matrix: every one of the n^2 cells has to move, and the rotation has to happen inside the matrix you were given rather than in a second one.

Input format: dojo passes the image as a plain list of lists of ints — matrix: list[list[int]], square, exactly as the constraints describe — and grades the rotation by the state of THAT matrix after the call, not by a returned value: the function returns nothing (None), and a solution that builds a new matrix and rebinds the name (or returns it) leaves everything the judge can see unchanged, so it fails. Rotate [[1, 2], [3, 4]] by writing into that same matrix to get [[3, 1], [4, 2]].
"""
