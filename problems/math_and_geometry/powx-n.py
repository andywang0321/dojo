"""Pow(x, n) [Medium]

Implement pow(x, n), which calculates x raised to the power n (i.e., x^n).
Example 1:
Input: x = 2.00000, n = 10
Output: 1024.00000
Example 2:
Input: x = 2.10000, n = 3
Output: 9.26100
Example 3:
Input: x = 2.00000, n = -2
Output: 0.25000
Explanation: 2^-2 = 1/2^2 = 1/4 = 0.25
Constraints:
* -100.0 < x < 100.0
* -2^31 <= n <= 2^31-1
* n is an integer.
* Either x is not zero or n > 0.
* -10^4 <= x^n <= 10^4

You should aim for a solution as good or better than O(log n) time and O(1) space, where n is the absolute value of the exponent: binary exponentiation squares the base and halves the exponent, so the loop runs once per bit of |n|, and the iterative form keeps the space O(1) - which is not decoration, since |n| can reach 2^31 - 1 and a recursion that deep would not survive Python's stack.
"""
