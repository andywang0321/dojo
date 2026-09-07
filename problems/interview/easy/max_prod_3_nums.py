# D.E. Shaw: Given an integer array, return the maximum product of any three numbers in the array. For example, for `A = [1, 3, 4, 5]`, you should return 60, while for `B = [-2, -4, 5, 3]`, you should return 40.

from typing import List, Any
import heapq

def max_tri_prod(A: List[int]) -> int:
    assert len(A) >= 3, 'len(input) must be >= 3!'
    largest = heapq.nlargest(3, A)
    smallest = heapq.nsmallest(2, A)
    return max(
        largest[0] * largest[1] * largest[2],
        smallest[0] * smallest[1] * largest[0]
    )

def main() -> None:
    A = [1, 3, 4, 5]
    B = [-2, -4, 5, 3]
    assert max_tri_prod(A) == 60, 'positive case failed!'
    assert max_tri_prod(B) == 40, 'negative case failed!'
    print('All tests passed!')

if __name__ == '__main__':
    main()
