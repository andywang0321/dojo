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


def test_pattern_for_tags_most_specific_wins():
    # LeetCode lists tags alphabetically — specificity, not position, decides
    # (v0.10.10): best-time-to-buy carries array + dynamic-programming +
    # sliding-window and must bucket into sliding_window.
    assert pattern_for_tags(
        ["array", "dynamic-programming", "sliding-window"]
    ) == "sliding_window"
    assert pattern_for_tags(["graph", "depth-first-search"]) == "graphs"
    assert pattern_for_tags(["depth-first-search", "graph"]) == "graphs"
    assert pattern_for_tags(["array", "string"]) == "arrays_and_hashing"


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


# -------------------------------------------------- bulk fetch (v0.10.10)

def test_roadmap_entries_slugs():
    from dojo.cli import _roadmap_entries

    entries = dict(_roadmap_entries())
    assert entries[1] == "two-sum"
    assert entries[121] == "best-time-to-buy-and-sell-stock"


def test_roadmap_lc_for_slug():
    from dojo.cli import _roadmap_lc_for_slug

    assert _roadmap_lc_for_slug("two-sum") == 1
    assert _roadmap_lc_for_slug("best-time-to-buy-and-sell-stock") == 121
    assert _roadmap_lc_for_slug("not-a-real-problem") is None


def test_cmd_fetch_all_skips_existing_and_tags_lc(db, monkeypatch, tmp_path):
    """The bulk runner lands only the missing roadmap problems, tags each
    with its LeetCode number (the fetcher model doesn't carry it), and
    survives per-problem failures."""
    from dojo.cli import _cmd_fetch_all
    from dojo.db import now
    from dojo.fetcher import LeetCodeError, ParsedProblem

    # The bulk runner binds DB_PATH/PROBLEMS_DIR from dojo.config at call
    # time (lazy import) — patch the config module, not cli.
    monkeypatch.setattr("dojo.config.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.config.PROBLEMS_DIR", tmp_path / "problems")
    (tmp_path / "problems").mkdir()
    # The seeded problem's seed FILE must exist too — file-aware skipping
    # treats a row without its file as a lost import and re-fetches it.
    (tmp_path / "problems" / "arrays_and_hashing").mkdir(parents=True)
    (tmp_path / "problems" / "arrays_and_hashing" / "contains-duplicate.py").write_text(
        '"""t [Easy]\n\nStatement."""\n'
    )

    # One problem already in the bank (skipped), the rest land.
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, lc_number, created_at) "
        "VALUES ('contains-duplicate', 't', 'Easy', 'arrays_and_hashing', 's', 217, ?)",
        (now(),),
    )
    db.commit()

    calls = []

    def fake_fetch(slug):
        calls.append(slug)
        if slug == "trapping-rain-water":
            raise LeetCodeError("rate limited")
        return ParsedProblem(
            title_slug=slug,
            title=slug,
            difficulty="Easy",
            pattern="arrays_and_hashing",
            statement=f"{slug} [Easy]\n\nStatement.",
            function_name="solve_it",
            signature="(x: int) -> int",
            url="https://example.com",
        )

    def fake_land(problem, problems_dir, db_path):
        from dojo.db import connect, now as _now

        with connect(db_path) as conn:
            conn.execute(
                "INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at) "
                "VALUES (?, ?, 'Easy', ?, ?, ?)",
                (problem.title_slug, problem.title, problem.pattern, problem.statement, _now()),
            )
            conn.commit()
        return problems_dir / problem.pattern / f"{problem.title_slug}.py"

    monkeypatch.setattr("dojo.fetcher.fetch_problem", fake_fetch)
    monkeypatch.setattr("dojo.fetcher.land", fake_land)

    console = type("C", (), {"print": lambda self, *a, **k: None})()
    exit_code = _cmd_fetch_all(console, delay=0)

    # 217 skipped (in bank); 1 two-sum landed; 42 trapping failed.
    assert "contains-duplicate" not in calls
    assert "two-sum" in calls
    assert exit_code == 1  # the trapping failure is reported, not fatal

    with __import__("dojo.db", fromlist=["connect"]).connect(tmp_path / "dojo.db") as conn:
        row = conn.execute(
            "SELECT lc_number FROM problems WHERE slug = 'two-sum'"
        ).fetchone()
    assert row["lc_number"] == 1


def test_reseed_does_not_wipe_tagged_lc(tmp_path):
    """Regression (v0.10.10): the bank importer's upsert once overwrote a
    tagged lc_number with NULL on every reseed — COALESCE preserves it."""
    from dojo.bank import ensure_seeded

    problems_dir = tmp_path / "problems"
    db_path = tmp_path / "dojo.db"
    (problems_dir / "arrays_and_hashing").mkdir(parents=True)
    (problems_dir / "arrays_and_hashing" / "two-sum.py").write_text(
        '"""Two Sum [Easy]\n\nStatement."""\n'
    )
    ensure_seeded(db_path, problems_dir)
    from dojo.db import connect

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE problems SET lc_number = 1 WHERE slug = 'two-sum'"
        )
        conn.commit()
    ensure_seeded(db_path, problems_dir)  # reseed must not wipe the tag
    with connect(db_path) as conn:
        assert conn.execute(
            "SELECT lc_number FROM problems WHERE slug = 'two-sum'"
        ).fetchone()["lc_number"] == 1


def test_bulk_fetch_retags_when_a_stale_duplicate_owns_the_number(db, monkeypatch, tmp_path):
    """Regression (v0.13 follow-up): the bulk fetch's "already in the bank" test
    only asked whether the LeetCode number appeared *somewhere*, so a stale
    duplicate row could hold it while the seed row for the roadmap's own slug had
    none — and the problem was skipped forever, off the ladder (LC 50/208/235 in
    the live bank)."""
    from dojo.cli import _cmd_fetch_all

    monkeypatch.setattr("dojo.config.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.config.PROBLEMS_DIR", tmp_path / "problems")
    (tmp_path / "problems" / "arrays_and_hashing").mkdir(parents=True)
    (tmp_path / "problems" / "arrays_and_hashing" / "contains-duplicate.py").write_text(
        '"""Contains Duplicate [Easy]\n\nStatement."""\n'
    )
    # The live shape: the seed row for the roadmap slug exists with no tag,
    # while a stale duplicate row (no file, uncurated) owns the number.
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at) "
        "VALUES ('contains-duplicate', 'Contains Duplicate', 'Easy', "
        "'arrays_and_hashing', 's', '2026-01-01')"
    )
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, lc_number, created_at) "
        "VALUES ('contains_duplicate', 'Contains Duplicate', 'Easy', "
        "'arrays_and_hashing', 's', 217, '2026-01-01')"
    )
    db.commit()

    from dojo.fetcher import LeetCodeError

    calls: list[str] = []

    def fake_fetch(slug):
        # Everything else in the roadmap is "offline" — the point is only which
        # problems the runner decided it still needed.
        calls.append(slug)
        raise LeetCodeError("offline")

    monkeypatch.setattr("dojo.fetcher.fetch_problem", fake_fetch)
    console = type("C", (), {"print": lambda self, *a, **k: None})()
    _cmd_fetch_all(console, delay=0)

    from dojo.db import connect

    with connect(tmp_path / "dojo.db") as conn:
        row = conn.execute(
            "SELECT lc_number FROM problems WHERE slug = 'contains-duplicate'"
        ).fetchone()
    assert row["lc_number"] == 217      # the row that owns the problem got the tag
    assert "contains-duplicate" not in calls


def test_an_offline_leetcode_is_reported_in_plain_language():
    """The fetcher's transport is a different service from the AI backend, and
    gets the same plain-language line with the right noun (v0.13 follow-up)."""
    import urllib.error

    from dojo.fetcher import LeetCodeError
    from dojo.fetcher.leetcode import fetch_question_data
    from dojo.guard import network_message

    def offline_post(url, payload, headers):
        raise urllib.error.URLError("no route to host")

    with pytest.raises(LeetCodeError) as exc_info:
        fetch_question_data(offline_post, "two-sum")
    assert str(exc_info.value) == network_message("LeetCode")


def test_a_non_network_transport_failure_keeps_its_detail():
    from dojo.fetcher import LeetCodeError
    from dojo.fetcher.leetcode import fetch_question_data

    def broken_post(url, payload, headers):
        raise ValueError("the transport returned garbage")

    with pytest.raises(LeetCodeError, match="transport error: the transport returned garbage"):
        fetch_question_data(broken_post, "two-sum")
