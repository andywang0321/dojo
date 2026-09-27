"""Palindrome Partitioning [Medium]

Given a string s, partition s such that every substring of the partition is a palindrome. Return all possible palindrome partitioning of s.
Example 1:
Input: s = "aab"
Output: [["a","a","b"],["aa","b"]]
Example 2:
Input: s = "a"
Output: [["a"]]
Constraints:
* 1 <= s.length <= 16
* s contains only lowercase English letters.

You should aim for a solution as good or better than O(n * 2^n) time and O(n) space, where n is the length of s -- a partition is a choice among the n - 1 cut positions, so a string of one repeated letter has 2^(n-1) palindromic partitions and copying each costs up to n; testing a prefix for palindromicity before recursing past it is what keeps the walk on the palindromic ones instead of testing all 2^(n-1) cut sets.
"""
