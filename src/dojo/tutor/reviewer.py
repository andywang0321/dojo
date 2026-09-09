"""The reviewer: qualitative, post-submission critique.

Separate role from the tutor on purpose — the tutor guides during the solve,
the reviewer grades after it. One agent doing both would grade its own hints
and be tempted to repair the student's code.

Model output is schema-normalized before display/storage: rubric dimensions
may arrive as {"score", "comment"} dicts or as bare numbers, and the review
must render either way (v0.6 lesson from a real solve where the model
returned bare ints and the chart came out empty).
"""

from __future__ import annotations

from dojo.db import REVIEW_DIMS
from dojo.tutor.backend import AIBackend
from dojo.tutor.prompts import REVIEWER_SYSTEM, build_review_prompt


def normalize_review(raw: dict) -> dict:
    """Repair the model's shape variance: wrap bare-int dimensions into
    {"score", "comment"} dicts; leave everything else untouched."""
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    for dim in REVIEW_DIMS:
        value = out.get(dim)
        if isinstance(value, (int, float)):
            out[dim] = {"score": value, "comment": ""}
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
    return normalize_review(backend.chat_json(REVIEWER_SYSTEM, prompt))
