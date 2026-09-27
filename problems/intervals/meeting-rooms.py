"""
Meeting Rooms [Easy]

Given an array of meeting time intervals where intervals[i] = [start_i, end_i], determine whether a person could attend all of the meetings.

Two meetings can be attended back to back when one ends exactly when the next one starts.

Example 1:
Input: intervals = [[0,30],[5,10],[15,20]]
Output: false
Explanation: the meeting from 0 to 30 overlaps both of the others.

Example 2:
Input: intervals = [[7,10],[2,4]]
Output: true
Explanation: the later meeting (2 to 4) finishes before the other starts (7).

Constraints:
* 0 <= intervals.length <= 10^4
* intervals[i].length == 2
* 0 <= start_i < end_i <= 10^6

You should aim for a solution as good or better than O(n log n) time and O(1) space, where n is the number of intervals.
"""
