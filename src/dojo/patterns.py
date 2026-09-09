"""The pattern taxonomy: which directories problems live in, and the
LeetCode topic-tag → pattern mapping that feeds the fetcher (v0.3).

One source of truth for both the bank's patterns and the curator's
validation, so the taxonomy can't drift between modules.
"""

PATTERNS = (
    "arrays_and_hashing",
    "stack",
    "two_pointers",
    "trees",
    "heap",
    "binary_search",
    "greedy",
    "dynamic_programming",
    "math",
    "linked_list",
    "graph",
    "backtracking",
    "sliding_window",
    "bit_manipulation",
)

# LeetCode topic-tag slugs that map cleanly onto a pattern (keyed by the
# GraphQL slug — stable across display-language changes). Everything else
# fails loudly in the fetcher rather than landing in a wrong bucket.
TAG_TO_PATTERN = {
    "array": "arrays_and_hashing",
    "hash-table": "arrays_and_hashing",
    "string": "arrays_and_hashing",
    "matrix": "arrays_and_hashing",
    "counting": "arrays_and_hashing",
    "sorting": "arrays_and_hashing",
    "prefix-sum": "arrays_and_hashing",
    "two-pointers": "two_pointers",
    "stack": "stack",
    "monotonic-stack": "stack",
    "tree": "trees",
    "binary-tree": "trees",
    "binary-search-tree": "trees",
    "depth-first-search": "trees",
    "breadth-first-search": "trees",
    "heap-priority-queue": "heap",
    "binary-search": "binary_search",
    "greedy": "greedy",
    "dynamic-programming": "dynamic_programming",
    "math": "math",
    "probability-and-statistics": "math",
    "linked-list": "linked_list",
    "graph": "graph",
    "union-find": "graph",
    "topological-sort": "graph",
    "shortest-path": "graph",
    "backtracking": "backtracking",
    "sliding-window": "sliding_window",
    "bit-manipulation": "bit_manipulation",
}


def pattern_for_tags(tag_slugs: list[str]) -> str:
    """First mapped tag wins (LeetCode orders tags by relevance); fail loudly
    when nothing maps, so a wrong bucket is never a silent accident."""
    if not tag_slugs:
        raise ValueError("problem has no topic tags; cannot choose a pattern")
    for slug in tag_slugs:
        if slug in TAG_TO_PATTERN:
            return TAG_TO_PATTERN[slug]
    raise ValueError(
        f"no topic tag maps to a dojo pattern (tags: {', '.join(tag_slugs)}); "
        "curate by hand or extend dojo/patterns.py"
    )
