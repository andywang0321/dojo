"""The LeetCode fetcher (v0.3): GraphQL intake → seed statement + signature.

Tests are offline: they pin OUR contract against canned GraphQL-shaped
fixtures, never the live endpoint.
"""

import json

import pytest

from dojo.fetcher.htmltext import HTMLToText
from dojo.fetcher.leetcode import (
    LeetCodeError,
    fetch_question_data,
    land,
    parse_python_signature,
    parse_question,
    pattern_for_tags,
)

TWO_SUM_HTML = (
    "<p>Given an array of integers <code>nums</code>&nbsp;and an integer "
    "<code>target</code>, return <em>indices</em> of the two numbers such "
    "that they add up to <code>target</code>.</p>"
    "<p><strong class=\"example\">Example 1:</strong></p>"
    "<pre><strong>Input:</strong> nums = [2,7,11,15], target = 9<br>"
    "<strong>Output:</strong> [0,1]</pre>"
    "<ul><li>Only one valid answer exists.</li><li>You may not use the same "
    "element twice.</li></ul>"
    "<p>Complexity: O(n<sup>2</sup>) is fine as a start.</p>"
)

TWO_SUM_RAW = {
    "data": {
        "question": {
            "questionId": "1",
            "title": "Two Sum",
            "titleSlug": "two-sum",
            "difficulty": "Easy",
            "content": TWO_SUM_HTML,
            "topicTags": [
                {"name": "Array", "slug": "array"},
                {"name": "Hash Table", "slug": "hash-table"},
            ],
            "codeSnippets": [
                {
                    "lang": "Python3",
                    "langSlug": "python3",
                    "code": (
                        "class Solution:\n"
                        "    def twoSum(self, nums: List[int], target: int) -> List[int]:\n"
                        "        "
                    ),
                }
            ],
            "exampleTestcases": "nums = [2,7,11,15], target = 9\n[3,2,4]\n6",
        }
    }
}

LINKED_LIST_RAW = {
    "data": {
        "question": {
            "questionId": "206",
            "title": "Reverse Linked List",
            "titleSlug": "reverse-linked-list",
            "difficulty": "Easy",
            "content": "<p>Given the head of a singly linked list, reverse the list.</p>",
            "topicTags": [{"name": "Linked List", "slug": "linked-list"}],
            "codeSnippets": [
                {
                    "lang": "Python3",
                    "langSlug": "python3",
                    "code": (
                        "class Solution:\n"
                        "    def reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]:\n"
                        "        "
                    ),
                }
            ],
            "exampleTestcases": "head = [1,2,3,4,5]",
        }
    }
}

MIN_STACK_RAW = {
    "data": {
        "question": {
            "questionId": "155",
            "title": "Min Stack",
            "titleSlug": "min-stack",
            "difficulty": "Medium",
            "content": "<p>Design a stack that supports push, pop, top, and getMin.</p>",
            "topicTags": [{"name": "Stack", "slug": "stack"}],
            "codeSnippets": [
                {
                    "lang": "Python3",
                    "langSlug": "python3",
                    "code": (
                        "class MinStack:\n"
                        "    def __init__(self):\n"
                        "        \n"
                        "    def push(self, val: int) -> None:\n"
                        "        \n"
                        "    def pop(self) -> None:\n"
                        "        \n"
                        "    def top(self) -> int:\n"
                        "        \n"
                        "    def getMin(self) -> int:\n"
                        "        \n"
                    ),
                }
            ],
            "exampleTestcases": "[]",
        }
    }
}


# ---------------------------------------------------------------- html → text


def test_html_to_text_paragraphs_and_code():
    text = HTMLToText().convert(TWO_SUM_HTML)
    assert "Given an array of integers nums and an integer target" in text
    assert "Example 1:" in text
    assert "Input: nums = [2,7,11,15], target = 9" in text
    assert "Output: [0,1]" in text
    assert "Only one valid answer exists." in text
    assert "O(n^2) is fine as a start." in text  # sup → ^, no markup


def test_html_to_text_superscripts_and_bullets():
    text = HTMLToText().convert(
        "<ul><li>\t2 &lt;= nums.length &lt;= 10<sup>4</sup></li>"
        "<li>-10<sup>9</sup> &lt;= nums[i]</li></ul>"
    )
    assert "* 2 <= nums.length <= 10^4" in text
    assert "* -10^9 <= nums[i]" in text
    assert "\t*" not in text
    assert "\n\t\n" not in text  # no whitespace-only lines between bullets


def test_html_to_text_strips_all_markup():
    text = HTMLToText().convert("<p><strong>bold</strong> and <em>em</em> "
                                "and <code>code</code>.</p>")
    assert text == "bold and em and code."


# ------------------------------------------------------------ signature parse


def test_parse_python_signature_function():
    parsed = parse_python_signature(TWO_SUM_RAW["data"]["question"]["codeSnippets"][0]["code"])
    assert parsed == {
        "function_name": "twoSum",
        "signature": "(nums: list[int], target: int) -> list[int]",
    }


def test_parse_python_signature_optional_normalization():
    parsed = parse_python_signature(
        "class Solution:\n    def f(self, x: Optional[List[int]]) -> None:\n        pass\n"
    )
    assert parsed == {
        "function_name": "f",
        "signature": "(x: list[int] | None) -> None",
    }


def test_parse_python_signature_class_methods():
    parsed = parse_python_signature(MIN_STACK_RAW["data"]["question"]["codeSnippets"][0]["code"])
    assert parsed["function_name"] == "MinStack"
    methods = parsed["signature"]["methods"]
    assert methods["push"] == "(self, val: int) -> None"
    assert methods["pop"] == "(self) -> None"
    assert methods["getMin"] == "(self) -> int"
    assert "__init__" not in methods


def test_parse_python_signature_without_annotations():
    parsed = parse_python_signature("class Solution:\n    def twoSum(self, nums, target):\n        pass\n")
    assert parsed == {"function_name": "twoSum", "signature": "(nums, target)"}


# ------------------------------------------------------------ tag → pattern


def test_pattern_for_tags_maps_known_slugs():
    assert pattern_for_tags(["array"]) == "arrays_and_hashing"
    assert pattern_for_tags(["linked-list"]) == "linked_list"
    assert pattern_for_tags(["heap-priority-queue"]) == "heap"
    assert pattern_for_tags(["union-find"]) == "graphs"
    assert pattern_for_tags(["sliding-window"]) == "sliding_window"
    assert pattern_for_tags(["backtracking"]) == "backtracking"
    assert pattern_for_tags(["bit-manipulation"]) == "bit_manipulation"
    assert pattern_for_tags(["binary-search"]) == "binary_search"
    assert pattern_for_tags(["trie"]) == "tries"
    assert pattern_for_tags(["interval"]) == "intervals"
    assert pattern_for_tags(["dynamic-programming"]) == "dp_1d"


def test_pattern_for_tags_first_match_wins():
    assert pattern_for_tags(["graph", "depth-first-search"]) == "graphs"
    assert pattern_for_tags(["depth-first-search", "graph"]) == "trees"


def test_pattern_for_tags_fails_on_unmapped():
    with pytest.raises(ValueError, match="rolling-hash"):
        pattern_for_tags(["rolling-hash"])
    with pytest.raises(ValueError, match="no topic tags"):
        pattern_for_tags([])


# ------------------------------------------------------------ question parse


def test_parse_question_two_sum():
    problem = parse_question(TWO_SUM_RAW)
    assert problem.title_slug == "two-sum"
    assert problem.title == "Two Sum"
    assert problem.difficulty == "Easy"
    assert problem.pattern == "arrays_and_hashing"
    assert problem.statement.startswith("Two Sum [Easy]")
    assert "Example 1:" in problem.statement
    assert problem.function_name == "twoSum"
    assert problem.signature == "(nums: list[int], target: int) -> list[int]"
    assert problem.url.endswith("/problems/two-sum/")


def test_parse_question_linked_list_pattern():
    problem = parse_question(LINKED_LIST_RAW)
    assert problem.pattern == "linked_list"
    assert problem.statement.startswith("Reverse Linked List [Easy]")


def test_parse_question_class_problem():
    problem = parse_question(MIN_STACK_RAW)
    assert problem.function_name == "MinStack"
    assert problem.signature == {
        "methods": {
            "push": "(self, val: int) -> None",
            "pop": "(self) -> None",
            "top": "(self) -> int",
            "getMin": "(self) -> int",
        }
    }


def test_parse_question_unknown_problem_raises():
    with pytest.raises(LeetCodeError, match="unknown problem"):
        parse_question({"data": {"question": None}})


# ------------------------------------------------------------ transport


def test_fetch_question_data_posts_graphql():
    calls = []

    def fake_post(url, payload, headers):
        calls.append((url, payload, headers))
        return 200, json.dumps(TWO_SUM_RAW)

    raw = fetch_question_data(fake_post, "two-sum")
    assert raw["data"]["question"]["title"] == "Two Sum"
    url, payload, headers = calls[0]
    assert "graphql" in url
    assert "questionData" in payload["query"]
    assert payload["variables"] == {"titleSlug": "two-sum"}
    assert "User-Agent" in headers


def test_fetch_question_data_transport_errors():
    with pytest.raises(LeetCodeError, match="HTTP 429"):
        fetch_question_data(lambda *a, **k: (429, "slow down"), "x")
    with pytest.raises(LeetCodeError, match="not JSON"):
        fetch_question_data(lambda *a, **k: (200, "not json"), "x")
    with pytest.raises(LeetCodeError, match="transport"):
        fetch_question_data(lambda *a, **k: (_ for _ in ()).throw(OSError("net down")), "x")


# ------------------------------------------------------------ landing


def test_land_writes_seed_and_reseeds(tmp_path):
    from dojo.bank import parse_problem_file
    from dojo.db import connect, init_db

    problems_dir = tmp_path / "problems"
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    problem = parse_question(TWO_SUM_RAW)

    land(problem, problems_dir=problems_dir, db_path=db_path)

    path = problems_dir / "arrays_and_hashing" / "two-sum.py"
    parsed = parse_problem_file(path)
    assert parsed is not None and parsed.title == "Two Sum"
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM problems WHERE slug='two-sum'").fetchone()
    assert row is not None
    assert row["function_name"] is None  # landed uncurated; the curator upgrades it


def test_land_refuses_existing_slug(tmp_path):
    from dojo.db import init_db

    problems_dir = tmp_path / "problems"
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    problem = parse_question(TWO_SUM_RAW)
    land(problem, problems_dir=problems_dir, db_path=db_path)
    with pytest.raises(LeetCodeError, match="already in the bank"):
        land(problem, problems_dir=problems_dir, db_path=db_path)
