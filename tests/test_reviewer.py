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
