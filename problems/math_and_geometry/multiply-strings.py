"""Multiply Strings [Medium]

Given two non-negative integers num1 and num2 represented as strings, return the product of num1 and num2, also represented as a string.
Note: You must not use any built-in BigInteger library or convert the inputs to integer directly.
Example 1:
Input: num1 = "2", num2 = "3"
Output: "6"
Example 2:
Input: num1 = "123", num2 = "456"
Output: "56088"
Constraints:
* 1 <= num1.length, num2.length <= 200
* num1 and num2 consist of digits only.
* Both num1 and num2 do not contain any leading zero, except the number 0 itself.

You should aim for a solution as good or better than O(m * n) time and O(m + n) space, where m and n are the lengths of num1 and num2: the intended grade-school multiplication multiplies every digit of one number by every digit of the other and accumulates the carries into a result of at most m + n digits.

Representation: the answer is the decimal string itself, and dojo compares it with exact equality - digits only, no leading zeros, no surrounding whitespace, and "0" for a zero product - so an answer that is right but spelled differently fails. The statement's ban on big-integer libraries and on converting the inputs to int is a rule on your implementation that the grader cannot see (`str(int(num1) * int(num2))` would be graded correct), which is why the reviewer reads your submitted code.
"""
