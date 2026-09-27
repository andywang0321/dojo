"""Reverse Bits [Easy]

Reverse bits of a given 32 bits signed integer.
Example 1:
Input: n = 43261596
Output: 964176192
Explanation:
			Integer
			Binary
			43261596
			00000010100101000001111010011100
			964176192
			00111001011110000010100101000000
Example 2:
Input: n = 2147483644
Output: 1073741822
Explanation:
			Integer
			Binary
			2147483644
			01111111111111111111111111111100
			1073741822
			00111111111111111111111111111110
Constraints:
* 0 <= n <= 2^31 - 2
* n is even.
Follow up: If this function is called many times, how would you optimize it?

You should aim for a solution as good or better than O(1) time and O(1) space, where n is the input value: the word is 32 bits wide, so the reversal is a fixed 32 steps and neither cost grows with n.

Input format: dojo passes n as a Python int, not a fixed-width machine word — its value is within 0 <= n <= 2^32 - 1, and every graded case stays inside the statement's own bound (0 <= n <= 2^31 - 2, with n even), so bit 31 is never set and the statement's "signed" wording cannot change the answer. Return the reversed value the same way, as a Python int.
"""
