"""The never-solve boundary is architectural (AGENTS.md rule 1): the tutor
must never be able to see judge or curator code, not even by import. These
tests pin the boundary mechanically."""

from pathlib import Path

import dojo.tutor


def test_tutor_sources_never_reference_judge_or_curator():
    package = Path(dojo.tutor.__file__).parent
    for path in package.rglob("*.py"):
        text = path.read_text()
        assert "dojo.judge" not in text, f"{path.name} references dojo.judge"
        assert "dojo.curator" not in text, f"{path.name} references dojo.curator"
        assert "dojo.fetcher" not in text, f"{path.name} references dojo.fetcher"
        assert "ORACLES" not in text, f"{path.name} references ORACLES"
        assert "CHECKERS" not in text, f"{path.name} references CHECKERS"


def test_tutor_prompt_builder_carries_no_solution_data():
    """The tutor prompt receives only: statement, student code, tier, hint
    history. Nothing registry-shaped may appear in what the model sees."""
    from dojo.tutor.prompts import build_tutor_prompt

    prompt = build_tutor_prompt(
        "Return true if the bracket string is valid.",
        "def is_valid(s): pass",
        2,
        "help",
        [{"tier": 1, "user": "stuck", "hint": "think LIFO"}],
    )
    lowered = prompt.lower()
    for forbidden in ("oracles", "registry", "dojo.judge", "expected_time", "profiler"):
        assert forbidden not in lowered, f"'{forbidden}' leaked into the tutor prompt"
    assert "def is_valid" in prompt  # student code is there
    assert "Return true" in prompt  # statement is there


def test_teacher_prompt_carries_topic_only():
    """Learning mode is a deliberate, documented narrowing of the never-solve
    boundary (v0.8): the teacher may teach topic-canonical code, but its
    context is the topic name and the conversation — never a problem
    statement or any solution-shaped data."""
    from dojo.tutor.prompts import TEACHER_SYSTEM, build_teacher_prompt

    prompt = build_teacher_prompt(
        "heap", [{"role": "student", "text": "why is peek O(1)?"}]
    )
    lowered = prompt.lower()
    for forbidden in (
        "oracles",
        "registry",
        "dojo.judge",
        "problem statement",
        "expected_time",
        "profiler",
    ):
        assert forbidden not in lowered, f"'{forbidden}' leaked into the teacher prompt"
    assert "topic: heap" in lowered
    assert "why is peek o(1)?" in lowered  # the conversation is there
    # MockBackend keys the teacher branch on the system prompt; TEACHER_SYSTEM
    # must not collide with the discussion branch (or any tutor branch).
    assert "tutor" not in TEACHER_SYSTEM.lower()
    assert "discussion" not in TEACHER_SYSTEM.lower()
