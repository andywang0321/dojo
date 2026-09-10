"""Tutor: AI-classified ladder vs discussion, leak re-audit + discard,
and Markdown stripping for terminal display."""

from dojo.tutor.backend import MockBackend
from dojo.tutor.prompts import build_tutor_prompt
from dojo.tutor.tutor import ask_tutor, de_markdown

STATEMENT = "Return true if the bracket string is valid."
CODE = "def is_valid(s: str) -> bool:\n    pass\n"

CANNED_LADDER = {
    "kind": "ladder",
    "tier": 2,
    "text": "Pattern hint: a data structure remembers the most recent opener.",
}
CANNED_DISCUSSION = {
    "kind": "discussion",
    "tier": None,
    "text": "Good question: sets give O(1) membership via hashing.",
}


class RecordingBackend:
    """Captures prompts; serves canned tutor JSON and audit ratings. Without
    a canned tutor, it synthesizes a ladder response echoing the requested
    tier (so tier-forcing is observable)."""

    def __init__(self, tutor=None, leak_ratings=None):
        self._tutor = tutor
        self._leak = leak_ratings if leak_ratings is not None else [1]
        self._rating_idx = 0
        self.prompts = []

    def chat(self, system, user):
        return ""

    def chat_json(self, system, user):
        self.prompts.append(user)
        if "auditor" in system.lower():
            rating = self._leak[min(self._rating_idx, len(self._leak) - 1)]
            self._rating_idx += 1
            return {"rating": rating, "rewritten": "" if rating < 3 else "SOFTENED"}
        if isinstance(self._tutor, list) and self._tutor:
            return self._tutor.pop(0)
        if self._tutor is not None:
            return self._tutor
        import re

        match = re.search(r"answer at tier (\d+)", user)
        tier = int(match.group(1)) if match else 1
        return {"kind": "ladder", "tier": tier, "text": f"Canned ladder answer at tier {tier}."}

    def tutor_prompts(self):
        return [p for p in self.prompts if "Audit it as JSON" not in p]


def test_vague_message_forces_tier_zero():
    backend = RecordingBackend()
    result = ask_tutor(backend, STATEMENT, CODE, tier=4, user_message="help", history=[])
    assert result.kind == "ladder"
    assert result.tier == 0
    assert any("tier 0" in p.lower() for p in backend.tutor_prompts())


def test_short_discussion_question_is_not_forced_to_tier_zero():
    """'what is a heap' is short but it is a discussion question, not a
    blockage — only ultra-short zero-information messages force tier 0."""
    backend = RecordingBackend()
    ask_tutor(backend, STATEMENT, CODE, tier=2, user_message="what is a heap", history=[])
    assert any("answer at tier 2" in p for p in backend.tutor_prompts())
    assert not any("answer at tier 0" in p for p in backend.tutor_prompts())


def test_ladder_kind_reports_tier_and_delivers():
    backend = RecordingBackend(tutor=[dict(CANNED_LADDER)])
    result = ask_tutor(
        backend,
        STATEMENT,
        CODE,
        tier=2,
        user_message="I tried counting brackets but it fails on '[(])' — what am I missing?",
        history=[],
    )
    assert result.kind == "ladder"
    assert result.tier == 2
    assert result.delivered
    assert result.leak_rating == 1


def test_discussion_kind_has_no_tier():
    backend = RecordingBackend(tutor=[dict(CANNED_DISCUSSION)])
    result = ask_tutor(
        backend,
        STATEMENT,
        CODE,
        tier=2,
        user_message="What are the permitted operations on a set?",
        history=[],
    )
    assert result.kind == "discussion"
    assert result.tier is None
    assert "sets give O(1)" in result.text


def test_leak_regenerates_until_clean_and_keeps_kind():
    backend = RecordingBackend(
        tutor=[dict(CANNED_LADDER), dict(CANNED_DISCUSSION)], leak_ratings=[5, 1]
    )
    result = ask_tutor(
        backend,
        STATEMENT,
        CODE,
        tier=2,
        user_message="Can you just give me the answer?",
        history=[],
    )
    assert result.leak_rating == 1
    assert result.kind == "ladder"  # the regeneration must not flip the mode
    assert result.delivered


def test_leak_discards_after_retries():
    backend = RecordingBackend(leak_ratings=[5, 5, 5])
    result = ask_tutor(
        backend,
        STATEMENT,
        CODE,
        tier=2,
        user_message="What is the full algorithm?",
        history=[],
    )
    assert result.delivered is False
    assert result.text == ""


def test_prompt_asks_for_classification():
    prompt = build_tutor_prompt(STATEMENT, CODE, 2, "question", [])
    assert "kind" in prompt
    assert "ladder" in prompt
    assert "discussion" in prompt


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


def test_de_markdown_blockquotes_rules_and_dunder_bold():
    text = "> a quoted insight\n\n__bold__ move\n\n---\n\n- item\n\n***"
    out = de_markdown(text)
    assert out == "a quoted insight\n\nbold move\n\n• item"
    assert "---" not in out and "***" not in out and "__" not in out


def test_mock_backend_teacher_branch():
    """The teacher branch keys on 'teacher' in the system prompt (learning
    mode, v0.8); a queue serves one canned reply per call and falls back to
    a default when exhausted, so a long conversation never crashes."""
    backend = MockBackend(teacher=["Primer about heaps.", "Because the root holds the min."])
    system = "You are a data structures teacher."
    assert backend.chat(system, "TOPIC: heap") == "Primer about heaps."
    assert backend.chat(system, "TOPIC: heap") == "Because the root holds the min."
    fallback = backend.chat(system, "TOPIC: heap")
    assert "heap" in fallback.lower() and len(fallback) > 0
