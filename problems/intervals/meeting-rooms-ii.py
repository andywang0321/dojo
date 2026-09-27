"""
Meeting Rooms II [Medium]

Given an array of meeting time intervals where intervals[i] = [start_i, end_i], return the minimum number of conference rooms required so that no two meetings are held in the same room at the same time.

A meeting that ends at time t frees its room for a meeting that starts at t.

Example 1:
Input: intervals = [[0,30],[5,10],[15,20]]
Output: 2
Explanation: the meeting from 0 to 30 overlaps both of the others, and [5,10] and [15,20] do not overlap each other, so two rooms suffice.

Example 2:
Input: intervals = [[7,10],[2,4]]
Output: 1
Explanation: one of the two meetings finishes before the other starts, so one room is enough.

Constraints:
* 1 <= intervals.length <= 10^4
* intervals[i].length == 2
* 0 <= start_i < end_i <= 10^6

You should aim for a solution as good or better than O(n log n) time and O(n) space, where n is the number of intervals.
"""
