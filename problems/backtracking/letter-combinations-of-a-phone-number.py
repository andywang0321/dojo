"""Letter Combinations of a Phone Number [Medium]

Given a string containing digits from 2-9 inclusive, return all possible letter combinations that the number could represent. Return the answer in any order.
A mapping of digits to letters (just like on the telephone buttons) is given below. Note that 1 does not map to any letters.
Example 1:
Input: digits = "23"
Output: ["ad","ae","af","bd","be","bf","cd","ce","cf"]
Example 2:
Input: digits = "2"
Output: ["a","b","c"]
Constraints:
* 1 <= digits.length <= 4
* digits[i] is a digit in the range ['2', '9'].

You should aim for a solution as good or better than O(4^n * n) time and O(n) space, where n is the number of digits: a key carries at most four letters, so the answer holds at most 4^n combinations and each one costs n characters to build, and the backtracking recursion that produces them is n deep (the returned list of combinations is not counted, as elsewhere in this corpus).
"""
