"""Word Search II [Hard]

Given an m x n board of characters and a list of strings words, return all words on the board.
Each word must be constructed from letters of sequentially adjacent cells, where adjacent cells are horizontally or vertically neighboring. The same letter cell may not be used more than once in a word.
Example 1:
Input: board = [["o","a","a","n"],["e","t","a","e"],["i","h","k","r"],["i","f","l","v"]], words = ["oath","pea","eat","rain"]
Output: ["eat","oath"]
Example 2:
Input: board = [["a","b"],["c","d"]], words = ["abcb"]
Output: []
Constraints:
* m == board.length
* n == board[i].length
* 1 <= m, n <= 12
* board[i][j] is a lowercase English letter.
* 1 <= words.length <= 3 * 10^4
* 1 <= words[i].length <= 10
* words[i] consists of lowercase English letters.
* All the strings of words are unique.

You should aim for a solution as good or better than O(n) time and O(n) space, where n is the total size of the input — the m x n board plus every character of words: build one trie over all the words and then walk the board once, instead of re-walking the board for every word the way a brute-force search does. (The statement caps the board at 12 x 12 and a word at 10 characters, so the 4^L backtracking factor is a constant fixed by those limits rather than something the input can grow.)
"""
