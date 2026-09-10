"""The pattern taxonomy: the dojo pattern set (v0.10 — NeetCode's 18
technique groups, in the roadmap's progression order), the LeetCode
topic-tag → pattern mapping that feeds the fetcher (v0.3), and the
progression gate.

One source of truth for the bank's patterns, the curator's validation,
and the roadmap's group mapping, so the taxonomy can't drift between
modules.
"""

# The 18 NeetCode roadmap groups, in progression order (v0.10). The
# `dojo learn` picker and the roadmap view both read this order.
PATTERNS = (
    "arrays_and_hashing",
    "two_pointers",
    "sliding_window",
    "stack",
    "binary_search",
    "linked_list",
    "trees",
    "tries",
    "heap",
    "backtracking",
    "graphs",
    "advanced_graphs",
    "dp_1d",
    "dp_2d",
    "greedy",
    "intervals",
    "math_and_geometry",
    "bit_manipulation",
)

# NeetCode display names → dojo pattern slugs (the roadmap.toml mapping).
GROUP_SLUGS = {
    "Arrays & Hashing": "arrays_and_hashing",
    "Two Pointers": "two_pointers",
    "Sliding Window": "sliding_window",
    "Stack": "stack",
    "Binary Search": "binary_search",
    "Linked List": "linked_list",
    "Trees": "trees",
    "Tries": "tries",
    "Heap / Priority Queue": "heap",
    "Backtracking": "backtracking",
    "Graphs": "graphs",
    "Advanced Graphs": "advanced_graphs",
    "1-D Dynamic Programming": "dp_1d",
    "2-D Dynamic Programming": "dp_2d",
    "Greedy": "greedy",
    "Intervals": "intervals",
    "Math & Geometry": "math_and_geometry",
    "Bit Manipulation": "bit_manipulation",
}

# The progression gate (v0.10): each pattern unlocks after the previous
# one in the roadmap order is complete (bank-wise). This is dojo's
# encoding of the verified group order — the mirrored data carries the
# order, not the site's explicit DAG edges; adjust here if a different
# edge set is ever wanted. The scheduler's hard gate reads this.
PREREQS = {
    pattern: (PATTERNS[i - 1],) for i, pattern in enumerate(PATTERNS) if i > 0
}


def prereqs_of(pattern: str) -> tuple[str, ...]:
    """The patterns that must be complete before ``pattern`` unlocks."""
    return PREREQS.get(pattern, ())


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
    "trie": "tries",
    "heap-priority-queue": "heap",
    "binary-search": "binary_search",
    "greedy": "greedy",
    # DP can't be split 1-D/2-D from a tag alone; dp_1d is the canonical
    # entry bucket (curation may re-bucket by hand).
    "dynamic-programming": "dp_1d",
    "math": "math_and_geometry",
    "probability-and-statistics": "math_and_geometry",
    "geometry": "math_and_geometry",
    "linked-list": "linked_list",
    "graph": "graphs",
    "union-find": "graphs",
    "topological-sort": "graphs",
    "shortest-path": "graphs",
    "backtracking": "backtracking",
    "sliding-window": "sliding_window",
    "interval": "intervals",
    "intervals": "intervals",
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
