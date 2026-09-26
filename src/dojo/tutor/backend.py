"""AI backends: a thin seam so tests and demos run without an API key.

**Roles, not prompt sniffing (v0.13).** Every call names the agent it belongs to
(`chat(Role.TUTOR, ...)`), and that name decides the system prompt's *address* in
the request, the output budget, the temperature, and — for `MockBackend` — which
canned answer comes back. Before this, the mock guessed the role from a substring
of the system prompt, which meant a *test fixture constrained product copy*:
`TEACHER_SYSTEM` was forbidden from containing the words "tutor" or
"discussion", and the discussion branch silently died once while the tests passed
against the wrong fallback.

**Providers, not a hardcoded host (v0.13).** `config.PROVIDERS` describes
DeepSeek, OpenAI and Anthropic; `DOJO_AI_BACKEND` / `DOJO_PROVIDER` picks one,
`DOJO_MODEL` overrides the model, and `DOJO_MODEL_<ROLE>` overrides it for one
role (a cheap model for the leak audit that runs on every hint, the strong one
for the review). Two wire formats are in play: OpenAI-compatible chat
completions (DeepSeek and OpenAI differ only by base URL, model and key) and
Anthropic's messages API, which takes the system prompt as a top-level field,
has no `response_format`, and returns JSON best via a forced tool call.

**Every request is bounded (v0.13 follow-up).** The SDKs default to a 600-second
read timeout and two retries. Against a connection that *opens and never answers*
— a captive portal, a dropped VPN, a sleeping router — that is up to half an hour
of a frozen terminal for one hint (measured: >600 s for a single call), which is
how "dojo crashed" was experienced offline. Each role carries its own timeout and
the retry count is one, so a stalled call fails while the student is still
watching. `DOJO_TIMEOUT` overrides the numbers for a slow provider or model.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from dojo import debuglog
from dojo.config import (
    PROVIDERS,
    Provider,
    ai_backend,
    resolve_key,
    role_model,
    timeout_override,
)

#: Output cap for JSON responses — generous because the reviewer's rubric is
#: the longest object the pipeline asks for, and a truncated (mid-object)
#: response is exactly the "non-JSON" failure real sessions saw.
JSON_MAX_TOKENS = 4096

#: How long a role waits for an answer, in seconds — two tiers, because the cost
#: of waiting is not the same everywhere. The interactive loop (a hint, the leak
#: rating on it, a discussion turn) has a student watching the cursor; the
#: long-form work (a rubric, a whole curation artifact set, a reference solution)
#: already happens outside the back-and-forth.
INTERACTIVE_TIMEOUT = 60.0
LONG_TIMEOUT = 180.0

#: Attempts per request (the SDK default is 2, which triples the wait). A retry
#: covers a transient blip; against a stalled connection it only doubles a wait
#: the student cannot distinguish from a hang.
REQUEST_RETRIES = 1


class Role(StrEnum):
    """Who is talking. The role is the backend's routing key and the provenance
    record stored on the attempt — never a substring of a prompt."""

    TUTOR = "tutor"
    DISCUSSION = "discussion"
    TEACHER = "teacher"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"  # the never-solve leak audit
    CURATOR = "curator"
    CURATION_AUDITOR = "curation_auditor"
    REFERENCER = "referencer"


@dataclass(frozen=True)
class Budget:
    """Per-role generation settings. The audit is a one-line JSON verdict and
    does not need the reviewer's budget; the reviewer needs room for a rubric.
    ``timeout`` is how long to wait for the answer (see `INTERACTIVE_TIMEOUT`)."""

    max_tokens: int = 2048
    temperature: float = 0.3
    timeout: float = INTERACTIVE_TIMEOUT


#: A cheap, tight audit is the point: it runs on *every* hint.
ROLE_BUDGETS: dict[Role, Budget] = {
    Role.AUDITOR: Budget(max_tokens=128, temperature=0.0),
    Role.TUTOR: Budget(),
    Role.DISCUSSION: Budget(),
    Role.REVIEWER: Budget(
        max_tokens=JSON_MAX_TOKENS, temperature=0.0, timeout=LONG_TIMEOUT
    ),
    Role.CURATOR: Budget(
        max_tokens=JSON_MAX_TOKENS, temperature=0.0, timeout=LONG_TIMEOUT
    ),
    Role.CURATION_AUDITOR: Budget(
        max_tokens=JSON_MAX_TOKENS, temperature=0.0, timeout=LONG_TIMEOUT
    ),
    Role.REFERENCER: Budget(
        max_tokens=JSON_MAX_TOKENS, temperature=0.0, timeout=LONG_TIMEOUT
    ),
    Role.TEACHER: Budget(timeout=LONG_TIMEOUT),
}


def budget_for(role) -> Budget:
    """The role's settings, with `DOJO_TIMEOUT` applied when it is set."""
    budget = ROLE_BUDGETS.get(Role(role), Budget())
    override = timeout_override()
    return replace(budget, timeout=override) if override is not None else budget


def parse_json_content(content: str) -> dict:
    """Parse model output as JSON, tolerating the shapes the API actually
    emits: the object may arrive fenced (```json ... ```) or wrapped in
    prose. Only content with no JSON object at all is an error."""
    if not content:
        return {"error": "model returned non-JSON"}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {"error": "model returned non-JSON"}


class AIBackend(Protocol):
    """Every agent talks through this. `role` is required and positional, so a
    new call site cannot silently inherit someone else's routing."""

    def chat(self, role, system: str, user: str) -> str: ...

    def chat_json(self, role, system: str, user: str) -> dict: ...

    def identity(self) -> dict: ...


class _LiveBackend:
    """Shared plumbing for the live backends: one call, one debug-log event that
    names the role, the provider and the model, so a log line is
    self-describing."""

    provider: Provider

    def identity(self) -> dict:
        return {
            "backend": self.provider.name,
            "model": role_model("reviewer", self.provider),
        }

    def _log(self, *, kind: str, role, system: str, user: str, **payload) -> None:
        debuglog.log_event(
            {
                "event": "ai",
                "kind": kind,
                "role": str(Role(role)),
                "provider": self.provider.name,
                "system": system,
                "user": user,
                **payload,
            }
        )

    def _log_error(self, *, kind: str, role, system: str, user: str, exc: Exception) -> None:
        debuglog.log_event(
            {
                "event": "backend_error",
                "kind": kind,
                "role": str(Role(role)),
                "provider": self.provider.name,
                "system": system,
                "user": user,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


class OpenAICompatBackend(_LiveBackend):
    """DeepSeek and OpenAI: the same chat-completions shape, different host, key
    and model. `client` is injectable so tests never touch the network."""

    def __init__(self, provider: Provider, api_key: str | None = None, client=None):
        self.provider = provider
        key = api_key or resolve_key(provider)
        if not key:
            raise RuntimeError(
                f"{provider.key_env} is not set. Export it, put it in a gitignored "
                ".env at the repo root, or run with DOJO_AI_BACKEND=mock."
            )
        if client is None:
            from openai import OpenAI  # local import: heavy dependency, lazy load

            client = OpenAI(
                api_key=key,
                base_url=provider.base_url,
                max_retries=REQUEST_RETRIES,  # the SDK's 2 triples a stalled wait
            )
        self._client = client

    def _create(self, role, system: str, user: str, *, as_json: bool):
        budget = budget_for(role)
        model = role_model(role, self.provider)
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": budget.temperature,
            "max_tokens": budget.max_tokens,
            # Per-request bound: without it a connection that never answers
            # holds the session for the SDK's 600-second default (v0.13 follow-up).
            "timeout": budget.timeout,
        }
        if as_json:
            kwargs["response_format"] = {"type": "json_object"}
        return self._client.chat.completions.create(**kwargs), model

    def chat(self, role, system: str, user: str) -> str:
        started = time.monotonic()
        try:
            response, model = self._create(role, system, user, as_json=False)
            content = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised
            self._log_error(kind="chat", role=role, system=system, user=user, exc=exc)
            raise
        self._log(
            kind="chat",
            role=role,
            system=system,
            user=user,
            model=model,
            raw=content,
            latency_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return content

    def chat_json(self, role, system: str, user: str) -> dict:
        started = time.monotonic()
        try:
            response, model = self._create(role, system, user, as_json=True)
            content = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised
            self._log_error(kind="chat_json", role=role, system=system, user=user, exc=exc)
            raise
        parsed = parse_json_content(content)
        self._log(
            kind="chat_json",
            role=role,
            system=system,
            user=user,
            model=model,
            raw=content,  # the response before parsing — the debugging gold
            parsed=parsed,
            latency_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return parsed


#: The one tool Anthropic is asked to call when a JSON object is wanted. Its
#: input schema is deliberately open — the roles ask for different shapes, and
#: the shapes are validated downstream (`reviewer.normalize_review`,
#: `curator.validate`).
JSON_TOOL = {
    "name": "emit_json",
    "description": "Return the requested result as a single JSON object.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    },
}


class AnthropicBackend(_LiveBackend):
    """Claude: system prompt top-level, `max_tokens` required, no
    `response_format` — JSON comes back as a forced tool call, with the tolerant
    text parser as the fallback (and the caller's retry behind that)."""

    def __init__(self, provider: Provider, api_key: str | None = None, client=None):
        self.provider = provider
        key = api_key or resolve_key(provider)
        if not key:
            raise RuntimeError(
                f"{provider.key_env} is not set. Export it, put it in a gitignored "
                ".env at the repo root, or run with DOJO_AI_BACKEND=mock."
            )
        if client is None:
            import anthropic  # local import: heavy dependency, lazy load

            client = anthropic.Anthropic(
                api_key=key,
                max_retries=REQUEST_RETRIES,  # the SDK's 2 triples a stalled wait
            )
        self._client = client

    def _create(self, role, system: str, user: str, *, as_json: bool):
        budget = budget_for(role)
        model = role_model(role, self.provider)
        kwargs = {
            "model": model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": budget.temperature,
            "max_tokens": budget.max_tokens,
            # Per-request bound: see OpenAICompatBackend._create.
            "timeout": budget.timeout,
        }
        if as_json:
            kwargs["tools"] = [JSON_TOOL]
            kwargs["tool_choice"] = {"type": "tool", "name": JSON_TOOL["name"]}
        return self._client.messages.create(**kwargs), model

    @staticmethod
    def _text_of(response) -> str:
        parts = []
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", "") or "")
        return "".join(parts)

    @staticmethod
    def _tool_input_of(response):
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "tool_use":
                value = getattr(block, "input", None)
                if isinstance(value, dict):
                    return value
        return None

    def chat(self, role, system: str, user: str) -> str:
        started = time.monotonic()
        try:
            response, model = self._create(role, system, user, as_json=False)
            content = self._text_of(response)
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised
            self._log_error(kind="chat", role=role, system=system, user=user, exc=exc)
            raise
        self._log(
            kind="chat",
            role=role,
            system=system,
            user=user,
            model=model,
            raw=content,
            latency_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return content

    def chat_json(self, role, system: str, user: str) -> dict:
        started = time.monotonic()
        try:
            response, model = self._create(role, system, user, as_json=True)
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised
            self._log_error(kind="chat_json", role=role, system=system, user=user, exc=exc)
            raise
        parsed = self._tool_input_of(response)
        raw = ""
        if parsed is None:
            # The model answered in prose instead of using the tool: fall back to
            # the same tolerant extractor every other backend uses.
            raw = self._text_of(response)
            parsed = parse_json_content(raw)
        self._log(
            kind="chat_json",
            role=role,
            system=system,
            user=user,
            model=model,
            raw=raw or json.dumps(parsed),
            parsed=parsed,
            latency_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return parsed


class MockBackend:
    """Deterministic canned backend, keyed on the **role** (v0.13).

    ``chat`` returns the canned answer for the role; ``chat_json`` serves the
    leak-check rating queue, a fixed review dict, and canned curator / reference
    / audit proposals. A list is consumed one entry per call and then repeats its
    last entry — a drained queue used to return `{}`, which surfaced in the
    student's terminal as a literal `{}` during a long offline demo."""

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
    DEFAULT_DISCUSSION = (
        "Post-solve discussion: you could also sort both arrays and walk two pointers."
    )

    def __init__(
        self,
        leak_ratings: list[int] | None = None,
        review: dict | None = None,
        curator: dict | None = None,
        tutor: dict | list | None = None,
        discussion: str = DEFAULT_DISCUSSION,
        auditor: dict | None = None,
        teacher: str | list | None = None,
        referencer: dict | None = None,
    ):
        self._leak_ratings = leak_ratings if leak_ratings is not None else [1]
        self._rating_idx = 0
        self._curator = curator or {}
        self._referencer = referencer or {}
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

    def identity(self) -> dict:
        return {"backend": "mock", "model": "mock"}

    @staticmethod
    def _canned(value, default):
        if not isinstance(value, list):
            return value
        if not value:
            return default
        return value.pop(0) if len(value) > 1 else value[0]

    def chat(self, role, system: str, user: str) -> str:
        role = Role(role)
        if role is Role.DISCUSSION:
            return self._discussion
        if role is Role.TEACHER:
            return self._canned(self._teacher, self.DEFAULT_TEACHER)
        for line in user.splitlines():
            if line.startswith("TIER="):
                tier = int(line.split("=")[1])
                return self.TIER_RESPONSES.get(tier, self.TIER_RESPONSES[1])
        return self.TIER_RESPONSES[1]

    def chat_json(self, role, system: str, user: str) -> dict:
        role = Role(role)
        if role is Role.AUDITOR:
            rating = self._leak_ratings[min(self._rating_idx, len(self._leak_ratings) - 1)]
            self._rating_idx += 1
            return {"rating": rating, "rewritten": "" if rating < 3 else "SOFTENED"}
        if role is Role.REVIEWER:
            return self._review
        if role is Role.REFERENCER:
            return self._canned(self._referencer, {})
        if role is Role.CURATION_AUDITOR:
            return self._auditor
        if role is Role.CURATOR:
            return self._canned(self._curator, {})
        if role is Role.TUTOR:
            return self._canned(self._tutor, {})
        return {}


def build_backend(name: str | None = None) -> AIBackend:
    """The backend for a provider name (default: the configured one)."""
    name = (name or ai_backend()).lower()
    if name == "mock":
        return MockBackend()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise RuntimeError(
            f"unknown AI backend '{name}' — use one of "
            f"{', '.join(sorted([*PROVIDERS, 'mock']))} (DOJO_AI_BACKEND / DOJO_PROVIDER)"
        )
    if provider.wire == "anthropic":
        return AnthropicBackend(provider)
    return OpenAICompatBackend(provider)


def get_backend() -> AIBackend:
    return build_backend()


__all__ = [
    "AIBackend",
    "AnthropicBackend",
    "Budget",
    "JSON_MAX_TOKENS",
    "JSON_TOOL",
    "MockBackend",
    "OpenAICompatBackend",
    "ROLE_BUDGETS",
    "Role",
    "budget_for",
    "build_backend",
    "get_backend",
    "parse_json_content",
]
