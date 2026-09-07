"""The tutor: gated hint ladder + leak audit.

Ladder policy (v0):
- tier 0 "articulate the blockage" — triggered when the student's message is
  too vague to be actionable; forcing metacognition before a hint.
- otherwise respond at the current tier and advance one tier for next time
  (capped at 5). The student can't get a deeper hint without trying in
  between — each `dojo hint` call is one rung.
- every response passes a leak audit (a second model call); anything rated
  >= 3 is regenerated, up to 2 retries.
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
    tier: int
    leak_rating: int


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


def ask_tutor(
    backend: AIBackend,
    statement: str,
    code: str,
    tier: int,
    user_message: str,
    history: list[dict],
) -> HintResult:
    if _vague(user_message):
        tier = 0
    prompt = build_tutor_prompt(statement, code, tier, user_message, history)
    response = backend.chat(TUTOR_SYSTEM, prompt)

    leak = backend.chat_json(LEAK_CHECK_SYSTEM, build_leak_prompt(response, tier))
    rating = int(leak.get("rating", 1))
    retries = 0
    while rating >= LEAK_THRESHOLD and retries < LEAK_RETRIES:
        rewritten = leak.get("rewritten") or ""
        response = (
            rewritten
            if rewritten and rewritten != "SOFTENED"
            else backend.chat(
                TUTOR_SYSTEM,
                prompt
                + "\n\nYour previous response was flagged as leaking too much "
                "of the solution. Answer again at the same tier, more guardedly.",
            )
        )
        leak = backend.chat_json(LEAK_CHECK_SYSTEM, build_leak_prompt(response, tier))
        rating = int(leak.get("rating", 1))
        retries += 1

    return HintResult(text=response, tier=tier, leak_rating=rating)
