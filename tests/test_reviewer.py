"""Reviewer: schema normalization, and reasoning/reflection feedback (v0.6)."""

from dojo.tutor.backend import MockBackend
from dojo.tutor.prompts import build_review_prompt
from dojo.tutor.reviewer import normalize_review, review


def test_normalize_wraps_bare_scores():
    raw = {
        "correctness": 4,
        "approach_quality": {"score": 5, "comment": "ok"},
        "broader_picture": "b",
        "overall_comment": "o",
    }
    out = normalize_review(raw)
    assert out["correctness"] == {"score": 4, "comment": ""}
    assert out["approach_quality"]["score"] == 5
    assert out["broader_picture"] == "b"


def test_normalize_passes_through_valid_shapes():
    raw = {"correctness": {"score": 5, "comment": "fine"}}
    assert normalize_review(raw) == raw


def test_review_returns_normalized_shapes():
    canned = {
        "correctness": 4,
        "complexity_reasoning": {"score": 5, "comment": "sound"},
    }
    out = review(
        MockBackend(review=canned),
        "s",
        "code",
        "O(n)",
        "O(n)",
        "O(n)",
        "O(n)",
        "O(n)",
        "O(n)",
    )
    assert out["correctness"] == {"score": 4, "comment": ""}
    assert out["complexity_reasoning"]["score"] == 5


def test_review_prompt_includes_reflection():
    prompt = build_review_prompt(
        "s", "c", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)",
        reflection="the key insight was the stack",
    )
    assert "STUDENT REFLECTION" in prompt
    assert "the key insight was the stack" in prompt


def test_normalize_clamps_out_of_range_scores():
    """A model answering on a 10-point scale (or 0) must not leak scores
    like 9/5 into the display — the rubric is 1-5, and normalization
    enforces it (belt and braces with the prompt's scale instruction)."""
    raw = {
        "correctness": 9,
        "approach_quality": {"score": 0, "comment": "?"},
        "style_idiom": {"score": 5, "comment": "fine"},
        "broader_picture": "b",
    }
    out = normalize_review(raw)
    assert out["correctness"]["score"] == 5
    assert out["approach_quality"]["score"] == 1
    assert out["style_idiom"]["score"] == 5


def test_review_retries_on_non_json():
    """A transient non-JSON response gets one retry instead of silently
    skipping the whole review (the reported first-submit failure). The
    retry goes through the plain chat path — repeating the exact
    temperature-0 request would reproduce the same failure — and its text
    is parsed with the same tolerant extractor."""

    class Flaky:
        def __init__(self):
            self.json_calls = 0

        def chat_json(self, role, system, user):
            self.json_calls += 1
            return {"error": "model returned non-JSON"}

        def chat(self, role, system, user):
            return '{"correctness": {"score": 4, "comment": "ok"}}'

    backend = Flaky()
    out = review(
        backend, "s", "code", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)"
    )
    assert backend.json_calls == 1
    assert out["correctness"]["score"] == 4


def test_review_parses_fenced_retry_text():
    """Even the retry's plain-text output may arrive fenced — the tolerant
    extractor applies there too."""

    class Fenced:
        def chat_json(self, role, system, user):
            return {"error": "model returned non-JSON"}

        def chat(self, role, system, user):
            return '```json\n{"correctness": {"score": 3, "comment": "ok"}}\n```'

    out = review(
        Fenced(), "s", "code", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)"
    )
    assert out["correctness"]["score"] == 3


def test_review_gives_up_after_retry():
    """Two non-JSON responses in a row: return the error so the caller skips
    the review gracefully (no crash, no half-review)."""

    class AlwaysFlaky:
        def chat_json(self, role, system, user):
            return {"error": "model returned non-JSON"}

        def chat(self, role, system, user):
            return "still not json at all"

    out = review(
        AlwaysFlaky(), "s", "code", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)", "O(n)"
    )
    assert "error" in out
