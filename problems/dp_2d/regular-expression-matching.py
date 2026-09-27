"""Regular Expression Matching [Hard]

Given an input string s and a pattern p, implement regular expression matching with support for '.' and '*' where:
* '.' Matches any single character.​​​​
* '*' Matches zero or more of the preceding element.
Return a boolean indicating whether the matching covers the entire input string (not partial).
Example 1:
Input: s = "aa", p = "a"
Output: false
Explanation: "a" does not match the entire string "aa".
Example 2:
Input: s = "aa", p = "a*"
Output: true
Explanation: '*' means zero or more of the preceding element, 'a'. Therefore, by repeating 'a' once, it becomes "aa".
Example 3:
Input: s = "ab", p = ".*"
Output: true
Explanation: ".*" means "zero or more (*) of any character (.)".
Constraints:
* 1 <= s.length <= 20
* 1 <= p.length <= 20
* s contains only lowercase English letters.
* p contains only lowercase English letters, '.', and '*'.
* It is guaranteed for each appearance of the character '*', there will be a previous valid character to match.

You should aim for a solution as good or better than O(m * n) time and O(m * n) space, where m is the length of s and n is the length of p: the intended table stores one boolean per (string position, pattern position) pair -- m * n states, each decided from at most two others -- and it is a table rather than a plain recursion because a '*' group can consume any number of characters, so the same state is reached by many different splits of the pattern; carrying the table in a single rolling row of n + 1 flags computes the same recurrence in O(n) space instead, which is at least as good.
"""
