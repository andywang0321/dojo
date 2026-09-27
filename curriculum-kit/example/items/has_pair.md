# Is there a pair that sums to the target? [intro]

Given a list of integers `values` and an integer `target`, return `True` if two
**distinct indices** `i != j` satisfy `values[i] + values[j] == target`, and `False`
otherwise.

## Examples

    Input: values = [3, 1, 4, 1, 5], target = 6
    Output: True            # values[1] + values[4], or values[3] + values[4]

    Input: values = [3, 1, 4], target = 8
    Output: False

    Input: values = [2, 2], target = 4
    Output: True            # two different indices, equal values

## Constraints

* `0 <= len(values) <= 100_000`
* `-10^9 <= values[i], target <= 10^9`
* The same index may not be used twice; equal values at different indices may.

## What to aim for

A single pass with a set of the values seen so far is `O(n)` time and `O(n)` space.
The obvious double loop is `O(n^2)` and passes every small case — this exercise is
also measured, so the difference shows up in the paired comparison rather than in the
checks.
