"""The reviewer: qualitative, post-submission critique.

Separate role from the tutor on purpose — the tutor guides during the solve,
the reviewer grades after it. One agent doing both would grade its own hints
and be tempted to repair the student's code.

Model output is schema-normalized before display/storage: rubric dimensions
may arrive as {"score", "comment"} dicts or as bare numbers, and the review
must render either way (v0.6 lesson from a real solve where the model
returned bare ints and the chart came out empty). Scores are clamped to the
rubric's 1-5 scale (a 10-point-scale model once shipped 9/5 scores), and a
transient non-JSON response gets one retry before the caller skips the
review (v0.8.1).
"""

from __future__ import annotations

from dojo.db import REVIEW_DIMS
from dojo.tutor.backend import AIBackend
from dojo.tutor.prompts import REVIEWER_SYSTEM, build_review_prompt


def _clamp(score) -> int | float:
    """Rubric scores are 1-5; anything outside that range (a model answering
    on a 10-point scale, or 0) is clamped rather than rescaled."""
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        return max(1, min(5, int(score)))
    return score


def normalize_review(raw: dict) -> dict:
    """Repair the model's shape variance: wrap bare-int dimensions into
    {"score", "comment"} dicts and clamp scores to 1-5; leave everything
    else untouched."""
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    for dim in REVIEW_DIMS:
        value = out.get(dim)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[dim] = {"score": _clamp(value), "comment": ""}
        elif isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
            out[dim] = {**value, "score": _clamp(value["score"])}
    return out


def review(
    backend: AIBackend,
    statement: str,
    code: str,
    claimed_time: str | None,
    claimed_space: str | None,
    measured_time: str | None,
    measured_space: str | None,
    expected_time: str | None,
    expected_space: str | None,
    static_analysis=None,
    reflection: str | None = None,
) -> dict:
    prompt = build_review_prompt(
        statement,
        code,
        claimed_time,
        claimed_space,
        measured_time,
        measured_space,
        expected_time,
        expected_space,
        static_analysis=static_analysis,
        reflection=reflection,
    )
    result = backend.chat_json(REVIEWER_SYSTEM, prompt)
    if isinstance(result, dict) and result.get("error"):
        retry = backend.chat_json(
            REVIEWER_SYSTEM,
            prompt
            + "\n\n(The previous response was not valid JSON. Respond with a "
            "single JSON object only — no prose outside it.)",
        )
        if not (isinstance(retry, dict) and retry.get("error")):
            result = retry
    return normalize_review(result)
