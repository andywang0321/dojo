"""The reviewer: qualitative, post-submission critique.

Separate role from the tutor on purpose — the tutor guides during the solve,
the reviewer grades after it. One agent doing both would grade its own hints
and be tempted to repair the student's code.
"""

from __future__ import annotations

from dojo.tutor.backend import AIBackend
from dojo.tutor.prompts import REVIEWER_SYSTEM, build_review_prompt


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
    )
    return backend.chat_json(REVIEWER_SYSTEM, prompt)
