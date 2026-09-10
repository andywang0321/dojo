"""AI backends: a thin seam so tests and demos run without an API key.

``DOJO_AI_BACKEND=mock`` gives canned, tier-driven responses. The default is
``deepseek`` (OpenAI-compatible client pointed at api.deepseek.com), which
requires ``DEEPSEEK_API_KEY`` in the environment or a gitignored ``.env``.
"""

from __future__ import annotations

import json
from typing import Protocol

from dojo.config import ai_backend, deepseek_api_key

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


class AIBackend(Protocol):
    def chat(self, system: str, user: str) -> str: ...

    def chat_json(self, system: str, user: str) -> dict: ...


class DeepSeekBackend:
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or deepseek_api_key()
        if not self._api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Export it, put it in a gitignored "
                ".env at the repo root, or run with DOJO_AI_BACKEND=mock."
            )
        from openai import OpenAI  # local import: heavy dependency, lazy load

        self._client = OpenAI(api_key=self._api_key, base_url=DEEPSEEK_BASE_URL)

    def chat(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    def chat_json(self, system: str, user: str) -> dict:
        response = self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(response.choices[0].message.content or "{}")
        except json.JSONDecodeError:
            return {"error": "model returned non-JSON"}


class MockBackend:
    """Deterministic canned backend. ``chat`` reads ``TIER=<n>`` from the
    user prompt and returns the canned response for that tier; ``chat_json``
    serves a leak-check rating queue, a fixed review dict, and a canned
    curator proposal."""

    TIER_RESPONSES = {
        0: "Before I nudge you: can you say, in one sentence, where exactly "
        "you're stuck? What have you tried so far?",
        1: "Conceptual nudge: think about what property the input must have "
        "at every intermediate step, and what you need to remember to verify it.",
        2: "Pattern hint: this problem is a classic member of a well-known "
        "pattern family. Which data structure naturally remembers 'the most "
        "recently opened thing'?",
        3: "Data-structure hint: the invariant you need is LIFO order. What "
        "built-in container gives you that in O(1) per operation?",
        4: "Edge-case hint: make sure you handle the input ending while "
        "something is still 'open', and closers arriving when nothing is open.",
        5: "Skeleton (no code): (1) scan left to right; (2) maintain a "
        "structure of openers; (3) on a closer, verify it matches the most "
        "recent opener; (4) at the end, check nothing is left open.",
    }

    DEFAULT_TEACHER = (
        "Heap primer: a heap is a tree that keeps the minimum (or maximum) at "
        "the root, giving O(1) peek and O(log n) insert/remove. Reach for it "
        "whenever you need repeated 'smallest so far' queries — like a "
        "priority queue. Why do you think we can't just sort once?"
    )

    def __init__(
        self,
        leak_ratings: list[int] | None = None,
        review: dict | None = None,
        curator: dict | None = None,
        tutor: dict | list | None = None,
        discussion: str = "Post-solve discussion: you could also sort both arrays and walk two pointers.",
        auditor: dict | None = None,
        teacher: str | list | None = None,
    ):
        self._leak_ratings = leak_ratings if leak_ratings is not None else [1]
        self._rating_idx = 0
        self._curator = curator or {}
        self._tutor = tutor if tutor is not None else [
            {"kind": "ladder", "tier": 0, "text": self.TIER_RESPONSES[0]}
        ]
        self._discussion = discussion
        self._auditor = auditor or {"findings": [], "verdict": "ok", "explanation": "clean"}
        self._teacher = teacher if teacher is not None else self.DEFAULT_TEACHER
        self._review = review or {
            "correctness": {"score": 4, "comment": "The reasoning holds; check the empty-input case."},
            "approach_quality": {"score": 4, "comment": "Natural choice for this problem class."},
            "style_idiom": {"score": 4, "comment": "Idiomatic; consider early returns."},
            "naming": {"score": 4, "comment": "Clear names."},
            "edge_cases": {"score": 3, "comment": "Empty input and unbalanced closers deserve explicit tests."},
            "complexity_claim_check": {"score": 4, "comment": "Claim matches the code and measurement."},
            "complexity_reasoning": {"score": 4, "comment": "The why is sound."},
            "reflection_feedback": "You captured the core insight; naming the pattern family would help recall.",
            "broader_picture": "This is the canonical 'stack as LIFO memory' pattern; the same invariant "
            "powers DFS, expression evaluation, and undo stacks in editors.",
            "overall_comment": "Solid. One habit to build: state your loop invariant out loud.",
        }

    def chat(self, system: str, user: str) -> str:
        if "discussion" in system.lower():
            return self._discussion
        if "teacher" in system.lower():  # learning mode (v0.8)
            if isinstance(self._teacher, list):
                return self._teacher.pop(0) if self._teacher else self.DEFAULT_TEACHER
            return self._teacher
        for line in user.splitlines():
            if line.startswith("TIER="):
                tier = int(line.split("=")[1])
                return self.TIER_RESPONSES.get(tier, self.TIER_RESPONSES[1])
        return self.TIER_RESPONSES[1]

    def chat_json(self, system: str, user: str) -> dict:
        if "curation auditor" in system.lower():
            return self._auditor
        if "auditor" in system.lower():
            rating = self._leak_ratings[min(self._rating_idx, len(self._leak_ratings) - 1)]
            self._rating_idx += 1
            return {"rating": rating, "rewritten": "" if rating < 3 else "SOFTENED"}
        if "rubric" in system.lower() or "review" in system.lower():
            return self._review
        if "curator" in system.lower():
            if isinstance(self._curator, list):
                return self._curator.pop(0) if self._curator else {}
            return self._curator
        if "tutor" in system.lower():
            if isinstance(self._tutor, list):
                return self._tutor.pop(0) if self._tutor else {}
            return self._tutor
        return {}


def get_backend() -> AIBackend:
    if ai_backend() == "mock":
        return MockBackend()
    return DeepSeekBackend()
