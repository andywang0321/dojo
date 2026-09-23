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

SINGLE_QUOTED = """'''
Two Sum [Easy]

You should aim for a solution with O(n) time and O(n) space.
'''
"""


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


def test_parse_single_quoted_docstring(tmp_path: Path):
    path = tmp_path / "two_sum.py"
    path.write_text(SINGLE_QUOTED)
    parsed = parse_problem_file(path)
    assert parsed is not None
    assert parsed.slug == "two_sum"
    assert parsed.title == "Two Sum"
    assert parsed.expected_time == "O(n)"


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


def test_repo_corpus_parses():
    """The seed corpus itself must conform to the prompt format — a problem
    file that fails to parse is invisible to `dojo list` and `dojo day`."""
    problems = discover_problems()
    assert len(problems) >= 30
    for p in problems:
        assert p.slug and p.title and p.difficulty and p.pattern and p.statement


# ------------------------------------------------- the mirror, both directions
# The reseed is additive, so a row whose file is gone stayed forever: 18
# kebab-case duplicates from the fetcher's naming convention beside the corpus's
# snake_case one, each also making `dojo list` and the roadmap show one problem
# twice (v0.13 follow-up).


def test_prune_removes_rows_whose_problem_file_is_gone(db, tmp_path: Path):
    from dojo.bank import prune_stale_problems

    problems = tmp_path / "problems"
    (problems / "stack").mkdir(parents=True)
    (problems / "stack" / "valid_parentheses.py").write_text(GOOD)
    seed_problems(db, problems)
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at) "
        "VALUES ('valid-parentheses', 'Valid Parentheses', 'Easy', 'stack', 's', '2026-01-01')"
    )
    db.commit()

    notes: list[str] = []
    pruned = prune_stale_problems(db, problems, note=notes.append)

    assert pruned == ["valid-parentheses"]
    assert db.execute(
        "SELECT COUNT(*) c FROM problems WHERE slug = 'valid-parentheses'"
    ).fetchone()["c"] == 0
    # The row whose file exists is untouched.
    assert db.execute(
        "SELECT COUNT(*) c FROM problems WHERE slug = 'valid_parentheses'"
    ).fetchone()["c"] == 1
    assert any("Pruned 1 bank row" in line for line in notes)


def test_prune_keeps_rows_that_carry_something(db, tmp_path: Path):
    """Cleanup may never destroy what a student earned."""
    from dojo.bank import prune_stale_problems
    from dojo.db import now

    problems = tmp_path / "problems"
    (problems / "stack").mkdir(parents=True)
    # Fileless rows: one attempted, one curated, one with a warm-up card.
    for slug in ("attempted_one", "curated_one", "carded_one"):
        db.execute(
            "INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at) "
            "VALUES (?, 't', 'Easy', 'stack', 's', ?)",
            (slug, now()),
        )
    db.execute("UPDATE problems SET function_name = 'f' WHERE slug = 'curated_one'")
    db.execute(
        "INSERT INTO users (name, created_at) VALUES ('andy', ?)", (now(),)
    )
    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, code, status, started_at, submitted_at) "
        "SELECT 1, id, 'solve', 'x', 'correct', ?, ? FROM problems "
        "WHERE slug = 'attempted_one'",
        (now(), now()),
    )
    db.execute(
        "INSERT INTO item_cards (user_id, slug, pattern, stability, difficulty, due_at, created_at) "
        "VALUES (1, 'carded_one', 'stack', 1.0, 5.0, ?, ?)",
        (now(), now()),
    )
    db.commit()

    notes: list[str] = []
    assert prune_stale_problems(db, problems, note=notes.append) == []
    assert db.execute("SELECT COUNT(*) c FROM problems").fetchone()["c"] == 3
    assert any("kept because they carry" in line for line in notes)


def test_prune_hands_the_ladder_number_to_the_row_that_owns_it(db, tmp_path: Path):
    """A stale duplicate can be the only row carrying the LeetCode number while
    the corpus row for the roadmap's title-slug has none — deleting it without
    handing the number over drops a roadmap problem off the ladder."""
    from dojo.bank import prune_stale_problems

    problems = tmp_path / "problems"
    (problems / "arrays_and_hashing").mkdir(parents=True)
    (problems / "arrays_and_hashing" / "contains-duplicate.py").write_text(GOOD)
    seed_problems(db, problems)          # row `contains-duplicate`, lc NULL
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, lc_number, created_at) "
        "VALUES ('contains_duplicate', 'Contains Duplicate', 'Easy', "
        "'arrays_and_hashing', 's', 217, '2026-01-01')"
    )
    db.commit()

    assert prune_stale_problems(db, problems, note=lambda *_: None) == ["contains_duplicate"]
    row = db.execute(
        "SELECT lc_number FROM problems WHERE slug = 'contains-duplicate'"
    ).fetchone()
    assert row["lc_number"] == 217


def test_prune_never_overwrites_an_existing_number(db, tmp_path: Path):
    from dojo.bank import prune_stale_problems

    problems = tmp_path / "problems"
    (problems / "arrays_and_hashing").mkdir(parents=True)
    (problems / "arrays_and_hashing" / "contains-duplicate.py").write_text(GOOD)
    seed_problems(db, problems)
    db.execute("UPDATE problems SET lc_number = 999 WHERE slug = 'contains-duplicate'")
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, lc_number, created_at) "
        "VALUES ('contains_duplicate', 'Contains Duplicate', 'Easy', "
        "'arrays_and_hashing', 's', 217, '2026-01-01')"
    )
    db.commit()

    prune_stale_problems(db, problems, note=lambda *_: None)
    row = db.execute(
        "SELECT lc_number FROM problems WHERE slug = 'contains-duplicate'"
    ).fetchone()
    assert row["lc_number"] == 999  # a conflict is a curation problem, not a silent fix


def test_ensure_seeded_prunes_and_is_idempotent(db, tmp_path: Path):
    from dojo.bank import ensure_seeded

    problems = tmp_path / "problems"
    (problems / "stack").mkdir(parents=True)
    (problems / "stack" / "valid_parentheses.py").write_text(GOOD)
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at) "
        "VALUES ('valid-parentheses', 't', 'Easy', 'stack', 's', '2026-01-01')"
    )
    db.commit()

    notes: list[str] = []
    ensure_seeded(tmp_path / "dojo.db", problems, note=notes.append)
    assert any("Pruned 1 bank row" in line for line in notes)
    notes.clear()
    ensure_seeded(tmp_path / "dojo.db", problems, note=notes.append)
    assert notes == []  # nothing left to prune
