"""The tutor: AI-classified ladder vs discussion, leak-audited.

One command, two modes the model picks (v0.6):
- "ladder": the student is stuck — respond at the current tier and advance
  (capped at 5); a vague message forces tier 0 (metacognition first).
- "discussion": the student is exploring, not blocked — answer directly, no
  tier, no forced progression. The never-solve boundary holds in both modes.

Every response passes the leak audit; a response that still scores >= 3
after retries is discarded and never shown.
"""

from __future__ import annotations

from dataclasses import dataclass

from dojo.tutor.backend import AIBackend
from dojo.tutor.prompts import (
    LEAK_CHECK_SYSTEM,
    TUTOR_SYSTEM,
    build_leak_prompt,
    build_tutor_prompt,
)

MAX_TIER = 5
VAGUE_LENGTH = 20
LEAK_THRESHOLD = 3
LEAK_RETRIES = 2

TIER_NAMES = {
    0: "articulate the blockage",
    1: "conceptual nudge",
    2: "pattern recognition",
    3: "data structure / invariant",
    4: "edge cases",
    5: "skeleton (no code)",
}


@dataclass
class HintResult:
    text: str
    tier: int | None
    leak_rating: int
    kind: str  # "ladder" | "discussion"
    delivered: bool = True


def _vague(message: str) -> bool:
    return len(message.strip()) < VAGUE_LENGTH


def de_markdown(text: str) -> str:
    """Strip Markdown artifacts for terminal display.

    The prompts instruct plain text, but models occasionally emit Markdown
    anyway; this is the belt-and-braces pass. Bullets are captured first,
    then all asterisks and backticks are removed, '#' headers are flattened,
    numbered lists are left as-is. Underscores are deliberately untouched —
    stripping them would mangle identifiers like ``two_sum``.
    """
    lines = []
    for line in text.replace("**", "").replace("`", "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and " " in stripped:
            header, _, rest = stripped.partition(" ")
            if set(header) == {"#"}:
                line = rest
        elif stripped.startswith("- ") or stripped.startswith("* "):
            line = "• " + stripped[2:]
        lines.append(line)
    return "\n".join(lines).replace("*", "")


def _tutor_call(backend: AIBackend, prompt: str, default_tier: int) -> tuple[str, int | None, str]:
    raw = backend.chat_json(TUTOR_SYSTEM, prompt)
    if not isinstance(raw, dict):
        return "ladder", default_tier, str(raw)
    kind = raw.get("kind")
    kind = kind if kind in ("ladder", "discussion") else "ladder"
    tier = raw.get("tier")
    if kind == "ladder":
        tier = int(tier) if isinstance(tier, int) and 0 <= tier <= MAX_TIER else default_tier
    else:
        tier = None
    text = str(raw.get("text", "") or "")
    if not text:  # the model ignored the schema — fall back to the raw payload
        text = str(raw)
    return kind, tier, text


def _audit(backend: AIBackend, text: str) -> int:
    leak = backend.chat_json(LEAK_CHECK_SYSTEM, build_leak_prompt(text, 0))
    try:
        return int(leak.get("rating", 1))
    except (TypeError, ValueError):
        return 1


def ask_tutor(
    backend: AIBackend,
    statement: str,
    code: str,
    tier: int,
    user_message: str,
    history: list[dict],
) -> HintResult:
    """Classify and answer, then leak-audit. A response still rated >= 3
    after retries is discarded — never shown to the student."""
    vague = _vague(user_message)
    if vague:
        tier = 0
    prompt = build_tutor_prompt(statement, code, tier, user_message, history)
    kind, response_tier, text = _tutor_call(backend, prompt, default_tier=tier)
    if vague:
        kind = "ladder"  # "stuck" with no words is always the metacognition path

    rating = _audit(backend, text)
    retries = 0
    while rating >= LEAK_THRESHOLD and retries < LEAK_RETRIES:
        flagged = (
            prompt
            + f"\n\nYour previous response was flagged as leaking too much of "
            f"the solution. Answer again more guardedly, keeping kind={kind}."
        )
        _, _, text = _tutor_call(backend, flagged, default_tier=tier)
        rating = _audit(backend, text)
        retries += 1

    if rating >= LEAK_THRESHOLD:
        return HintResult(
            text="",
            tier=response_tier if kind == "ladder" else None,
            leak_rating=rating,
            kind=kind,
            delivered=False,
        )
    return HintResult(
        text=text,
        tier=response_tier if kind == "ladder" else None,
        leak_rating=rating,
        kind=kind,
    )
