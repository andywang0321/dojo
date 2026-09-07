"""
Valid Anagram [Easy]

Given two strings s and t, return true if the two strings are anagrams of each other, otherwise return false.
An anagram is a string that contains the exact same characters as another string, but the order of the characters can be different.

Example 1:
Input: s = "racecar", t = "carrace"
Output: true

Example 2:
Input: s = "jar", t = "jam"
Output: false

Constraints:
s and t consist of lowercase English letters.

You should aim for a solution with O(n + m) time and O(1) space, where n is the length of the string s and m is the length of the string t.
"""


def valid_anagram(s: str, t: str) -> bool:
    if len(s) != len(t):
        return False
    s_hist: dict = {}
    t_hist: dict = {}
    for si, ti in zip(s, t):
        s_hist[si] = s_hist.get(si, 0) + 1
        t_hist[ti] = t_hist.get(ti, 0) + 1
    return s_hist == t_hist


def test() -> None:
    assert valid_anagram("racecar", "carrace"), "Case 1 failed!"
    assert not valid_anagram("jar", "jam"), "Case 2 failed!"
    assert not valid_anagram("jarr", "jar"), "Case 3 failed!"
    assert not valid_anagram("jarr", "jaar"), "Case 4 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
