"""
Alien Dictionary [Hard]

There is a new alien language that uses the English alphabet, but the order of its letters is unknown. You are given a list of strings words taken from the alien language's dictionary, sorted lexicographically according to the rules of that language. Return any string of the unique letters in the alien language in the correct order. If no valid order exists, return an empty string.

The relative order of two letters is revealed by adjacent words: comparing word[i] and word[i+1] character by character, the first position where they differ gives a letter that comes before the other. If a word is a prefix of the word after it, that pair is consistent; if a longer word comes before a shorter word that is its prefix, the list is invalid.

Example 1:
Input: words = ["wrt","wrf","er","ett","rftt"]
Output: "wertf"
Explanation: "wrt" before "wrf" gives t < f, "wrt" before "er" gives w < e, "er" before "ett" gives r < t, and "ett" before "rftt" gives e < r. Together these force w < e < r < t < f.

Example 2:
Input: words = ["z","x"]
Output: "zx"
Explanation: the only relation is z < x.

Example 3:
Input: words = ["z","x","z"]
Output: ""
Explanation: z < x and x < z are both implied, so no consistent order exists.

Example 4:
Input: words = ["abc","ab"]
Output: ""
Explanation: "abc" comes before "ab" although "ab" is its prefix, which no alphabet can explain.

Constraints:
* 1 <= words.length <= 100
* 1 <= words[i].length <= 100
* words[i] consists of only lowercase English letters.

You should aim for a solution as good or better than O(n) time and O(1) space, where n is the total number of characters across all the words.

Note: the answer is any string that lists each letter appearing in words exactly once, in an order consistent with every adjacent pair — it is not unique, and the judge accepts any of them. The empty string is the answer exactly when the list is unrecoverable: the implied relations contain a cycle, or a longer word is placed before its own prefix.
"""
