"""
Group Anagrams [Medium]

Given an array of strings strs, group all anagrams together into sublists. You may return the output in any order.
An anagram is a string that contains the exact same characters as another string, but the order of the characters can be different.

Example 1:
Input: strs = ["act","pots","tops","cat","stop","hat"]
Output: [["hat"],["act", "cat"],["stop", "pots", "tops"]]

Example 2:
Input: strs = ["x"]
Output: [["x"]]

Example 3:
Input: strs = [""]
Output: [[""]]

Constraints:
1 <= strs.length <= 1000.
0 <= strs[i].length <= 100
strs[i] is made up of lowercase English letters.

You should aim for a solution with O(m * n) time and O(m) space, where m is the number of strings and n is the length of the longest string.
"""


def group_anagrams(strs: list[str]) -> list[list[str]]:
    # helper: get histogram of letter distribution
    def hist(s: str) -> tuple[int, ...]:
        h: list[int] = 26 * [0]
        for c in s:
            h[ord(c) - ord('a')] += 1
        return tuple(h)
    group_hist: dict = {hist(s): [] for s in strs}
    for s in strs:
        group_hist[hist(s)].append(s)
    return list(group_hist.values())


def test() -> None:
    import itertools

    def scramble(list_of_lists: list[list[str]]) -> tuple[list[list[str]]]:
        results: list = []
        # Generate all permutations of the outer list.
        for outer_perm in itertools.permutations(list_of_lists):
            # For each inner list in the current outer permutation, get all its permutations.
            inner_permutations: list = [list(itertools.permutations(inner)) for inner in outer_perm]
            # Combine the permutations of the inner lists using a Cartesian product.
            for inner_combo in itertools.product(*inner_permutations):
                results.append([list(c) for c in inner_combo])
        return tuple(results)

    assert group_anagrams(["act","pots","tops","cat","stop","hat"]) in scramble([["hat"],["act", "cat"],["stop", "pots", "tops"]]), "Case 1 failed!"
    assert group_anagrams(["x"]) == [["x"]], "Case 2 failed!"
    assert group_anagrams([""]) == [[""]], "Case 3 failed!"
    assert group_anagrams(["act", "aact", "hello", "cat"]) in scramble([["aact"], ["act", "cat"], ["hello"]]), "Case 4 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
