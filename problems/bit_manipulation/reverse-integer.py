"""Reverse Integer [Medium]

Given a signed 32-bit integer x, return x with its digits reversed. If reversing x causes the value to go outside the signed 32-bit integer range [-2^31, 2^31 - 1], then return 0.
Assume the environment does not allow you to store 64-bit integers (signed or unsigned).
Example 1:
Input: x = 123
Output: 321
Example 2:
Input: x = -123
Output: -321
Example 3:
Input: x = 120
Output: 21
Constraints:
* -2^31 <= x <= 2^31 - 1

You should aim for a solution as good or better than O(log n) time and O(1) space, where n is the number of digits in x: one pass over the digits, at most 10 of them under the 32-bit constraint above, and no more state than the reversed value itself.

Input format: dojo passes one plain Python int and grades the returned int — the reversed value, or 0 when the reversal leaves [-2^31, 2^31 - 1]. The statement's 'the environment does not allow you to store 64-bit integers' line describes the C++/Java setting: Python ints are unbounded, so the overflow rule is graded by the value you return rather than by how you stored it, and that value alone decides whether a case passes.
"""
