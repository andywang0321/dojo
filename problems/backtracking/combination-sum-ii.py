"""Combination Sum II [Medium]

Given a collection of candidate numbers (candidates) and a target number (target), find all unique combinations in candidates where the candidate numbers sum to target.
Each number in candidates may only be used once in the combination.
Note: The solution set must not contain duplicate combinations.
Example 1:
Input: candidates = [10,1,2,7,6,1,5], target = 8
Output: 
[
[1,1,6],
[1,2,5],
[1,7],
[2,6]
]
Example 2:
Input: candidates = [2,5,2,1,2], target = 5
Output: 
[
[1,2,2],
[5]
]
Constraints:
* 1 <= candidates.length <= 100
* 1 <= candidates[i] <= 50
* 1 <= target <= 30

You should aim for a solution as good or better than O(n * 2^n) time and O(n) space, where n is the number of candidates -- each candidate is either taken once or skipped, so the search tree has at most 2^n nodes, and the problem's test data keeps the number of unique combinations that sum to the target under 150, so the search that actually runs is far smaller than that worst case. Sorting first is what lets the loop stop as soon as a value exceeds what is left of the target and lets a repeated value be skipped at its own level, so every combination is found once and none is repeated in the answer.
"""
