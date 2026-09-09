"""The fetcher (v0.3): LeetCode problem intake → seed statement + curator
hints. Fetched statements are intake material, not solution code — but keep
them out of tutor context anyway (tests/test_never_solve.py pins it)."""

from dojo.fetcher.leetcode import (
    GRAPHQL_URL,
    LeetCodeError,
    ParsedProblem,
    fetch_problem,
    fetch_question_data,
    land,
    parse_python_signature,
    parse_question,
)

__all__ = [
    "GRAPHQL_URL",
    "LeetCodeError",
    "ParsedProblem",
    "fetch_problem",
    "fetch_question_data",
    "land",
    "parse_python_signature",
    "parse_question",
]
