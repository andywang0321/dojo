"""Bank seeding: docstring parsing and DB import."""

from pathlib import Path

from dojo.bank import discover_problems, load_overrides, parse_problem_file, seed_problems

GOOD = '''"""
Valid Parentheses [Easy]

You are given a string s consisting of brackets.
Return true if s is valid, false otherwise.

You should aim for a solution with O(n) time and O(n) space, where n is the length of the given string.
"""
'''

BAD_NO_DIFFICULTY = '''"""
Merge Sort Implementation
"""
'''

NOT_A_DOCSTRING = "# Amazon: intersection of two arrays\n"


def test_parse_problem_file(tmp_path: Path):
    path = tmp_path / "valid_parentheses.py"
    path.write_text(GOOD)
    parsed = parse_problem_file(path)
    assert parsed is not None
    assert parsed.slug == "valid_parentheses"
    assert parsed.title == "Valid Parentheses"
    assert parsed.difficulty == "Easy"
    assert parsed.expected_time == "O(n)"
    assert parsed.expected_space == "O(n)"


def test_parse_skips_nonconforming(tmp_path: Path):
    for name, content in [("mergesort.py", BAD_NO_DIFFICULTY), ("x.py", NOT_A_DOCSTRING)]:
        path = tmp_path / name
        path.write_text(content)
        assert parse_problem_file(path) is None


def test_discover_and_seed(db, tmp_path: Path):
    dsa = tmp_path / "dsa" / "stack"
    dsa.mkdir(parents=True)
    (dsa / "valid_parentheses.py").write_text(GOOD)
    (dsa / "mergesort.py").write_text(BAD_NO_DIFFICULTY)

    problems = discover_problems(dsa)
    assert len(problems) == 1
    assert problems[0].pattern == "stack"

    inserted = seed_problems(db, dsa)
    assert inserted == 1
    row = db.execute("SELECT * FROM problems WHERE slug='valid_parentheses'").fetchone()
    assert row["difficulty"] == "Easy"
    assert row["expected_time"] == "O(n)"


def test_load_overrides_from_repo():
    overrides = load_overrides()
    assert "valid_parentheses" in overrides
    ov = overrides["valid_parentheses"]
    assert ov.function_name == "is_valid"
    assert len(ov.visible_tests) >= 3
