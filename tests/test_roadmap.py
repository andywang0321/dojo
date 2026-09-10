"""Roadmap data (v0.10): the vendored NeetCode-150 progression parses
into 18 ordered groups whose problem ladders carry LeetCode numbers, and
the taxonomy's prereq chain matches the roadmap order."""

import pytest

from dojo.patterns import PATTERNS, prereqs_of
from dojo.roadmap import (
    RoadmapError,
    group_index,
    load_roadmap,
    next_ladder_problem,
)


@pytest.fixture()
def groups():
    return load_roadmap()


def test_roadmap_loads_18_groups_in_order(groups):
    assert [g["slug"] for g in groups] == list(PATTERNS)
    assert [g["order"] for g in groups] == list(range(1, 19))
    total = sum(len(g["problems"]) for g in groups)
    assert total == 150  # 149 mirrored + dojo's addendum (0271)


def test_roadmap_group_orders_match_taxonomy(groups):
    """The roadmap's group order is the progression: PATTERNS must mirror
    it exactly, or the picker/roadmap view and the prereq gate drift."""
    slugs = [g["slug"] for g in groups]
    for i, pattern in enumerate(PATTERNS):
        assert slugs[i] == pattern


def test_first_groups_ladders_are_canonical(groups):
    arrays = groups[0]
    assert arrays["problems"][:4] == [217, 242, 1, 49]  # duplicate, anagram, two-sum, group-anagrams
    assert 271 in arrays["problems"]  # the dojo addendum (the 150th problem)
    assert groups[1]["problems"][0] == 125  # two pointers starts with valid palindrome
    assert groups[7]["slug"] == "tries"


def test_prereq_chain_matches_roadmap_order():
    for i, pattern in enumerate(PATTERNS):
        if i == 0:
            assert prereqs_of(pattern) == ()
        else:
            assert prereqs_of(pattern) == (PATTERNS[i - 1],)


def test_next_ladder_problem_skips_solved_and_missing():
    groups = load_roadmap()
    bank = {217, 242, 1, 49}  # only the first four exist in the bank
    solved = {217, 242}
    assert next_ladder_problem(groups, "arrays_and_hashing", solved, bank) == 1
    solved = {217, 242, 1, 49}
    # 271 is on the ladder but not in the bank — skipped, not a blocker
    assert next_ladder_problem(groups, "arrays_and_hashing", solved, bank) is None
    assert next_ladder_problem(groups, "tries", set(), set()) is None


def test_unknown_group_name_fails_loudly(tmp_path):
    import tomllib

    path = tmp_path / "bad.toml"
    path.write_text(
        '[[groups]]\nname = "Mystery Group"\norder = 1\nproblems = ["0001_two_sum"]\n'
    )
    with pytest.raises(RoadmapError, match="Mystery Group"):
        load_roadmap(path)


def test_problem_without_number_prefix_fails_loudly(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        '[[groups]]\nname = "Arrays & Hashing"\norder = 1\nproblems = ["two_sum"]\n'
    )
    with pytest.raises(RoadmapError, match="two_sum"):
        load_roadmap(path)


def test_group_index():
    groups = load_roadmap()
    assert group_index(groups, "arrays_and_hashing") == 0
    assert group_index(groups, "bit_manipulation") == 17
    assert group_index(groups, "not_a_pattern") == -1
