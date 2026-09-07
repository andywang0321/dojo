"""Tutor hint ladder: tier gating, vagueness metacognition, leak re-audit,
and Markdown stripping for terminal display."""

from dojo.tutor.backend import MockBackend
from dojo.tutor.tutor import ask_tutor, de_markdown

STATEMENT = "Return true if the bracket string is valid."
CODE = "def is_valid(s: str) -> bool:\n    pass\n"


def test_vague_message_forces_tier_zero():
    result = ask_tutor(MockBackend(), STATEMENT, CODE, tier=4, user_message="help", history=[])
    assert result.tier == 0
    assert "where exactly you're stuck" in result.text


def test_specific_message_answers_at_current_tier():
    result = ask_tutor(
        MockBackend(),
        STATEMENT,
        CODE,
        tier=2,
        user_message="I tried counting brackets but it fails on '[(])' — what am I missing?",
        history=[],
    )
    assert result.tier == 2
    assert "data structure" in result.text  # canned tier-2 response
    assert result.leak_rating == 1


def test_leak_regenerates_until_clean():
    backend = MockBackend(leak_ratings=[5, 1])
    result = ask_tutor(
        backend,
        STATEMENT,
        CODE,
        tier=1,
        user_message="Can you just give me the answer?",
        history=[],
    )
    assert result.leak_rating == 1


def test_hint_history_is_passed_along():
    history = [{"tier": 1, "user": "stuck", "hint": "think about LIFO"}]
    result = ask_tutor(
        MockBackend(), STATEMENT, CODE, tier=2, user_message="still stuck on the closer case", history=history
    )
    assert result.tier == 2


def test_de_markdown_strips_artifacts():
    md = "**Key insight:** use a *stack*, not `str.count`.\n\n- first idea\n- second idea\n\n### Summary\nrest"
    out = de_markdown(md)
    assert "**" not in out and "`" not in out and "#" not in out
    assert out.startswith("Key insight: use a stack, not str.count.")
    assert "• first idea" in out and "• second idea" in out
    assert "Summary\nrest" in out


def test_de_markdown_keeps_underscores():
    # Underscores may be real identifiers (two_sum); only asterisk/backtick
    # artifacts are stripped.
    assert de_markdown("see `two_sum` and **hash_map**") == "see two_sum and hash_map"
