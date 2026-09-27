"""Longest Palindromic Substring [Medium]

Given a string s, return the longest palindromic substring in s.
Example 1:
Input: s = "babad"
Output: "bab"
Explanation: "aba" is also a valid answer.
Example 2:
Input: s = "cbbd"
Output: "bb"
Constraints:
* 1 <= s.length <= 1000
* s consist of only digits and English letters.

You should aim for a solution as good or better than O(n^2) time and O(1) space, where n is the length of s: expanding around every one of the 2n-1 centers is the intended solution, and Manacher's algorithm reaches O(n) time but is not required.
"""
