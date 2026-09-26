"""The tutor: AI-classified ladder vs discussion, leak-audited.

One command, two modes the model picks (v0.6):
- "ladder": the student is stuck — respond at the current tier and advance
  (capped at 5); a vague message forces tier 0 (metacognition first).
- "discussion": the student is exploring, not blocked — answer directly, no
  tier, no forced progression. The never-solve boundary holds in both modes.

Every response passes the leak audit; a response that still scores >= 3 after
retries is discarded and never shown — and so is a response the audit could not
read at all (v0.13). The audit used to fail **open**: a non-JSON reply, a missing
`rating`, a string rating, or a `None` rating all collapsed to "clean", so a full
solution was delivered in all four cases. The never-solve rule is enforced at
this boundary, which makes an unreadable audit a gap in the guarantee rather
than a pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from dojo.guard import is_network_error
from dojo.tutor.backend import AIBackend, Role
from dojo.tutor.prompts import (
    LEAK_CHECK_SYSTEM,
    TUTOR_SYSTEM,
    build_leak_prompt,
    build_tutor_prompt,
)

MAX_TIER = 5
# Only ultra-short messages ("stuck", "help" — zero information) force the
# metacognition tier. Slightly longer short questions ("what is a heap")
# are discussion, and the model classifies them.
VAGUE_LENGTH = 6
LEAK_THRESHOLD = 3
LEAK_RETRIES = 2
#: How many times an unreadable *audit* is retried before the response is
#: refused. The hint itself is fine — a JSON hiccup in the auditor must not cost
#: the student their answer — but it must never become a pass.
AUDIT_ATTEMPTS = 2

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
    leak_rating: int | None
    kind: str  # "ladder" | "discussion"
    delivered: bool = True
    #: True when the response was discarded because the *audit* failed, not
    #: because it leaked: the caller says so rather than blaming the answer.
    audit_failed: bool = False
    #: True when that audit failure was the backend being unreachable (v0.13
    #: follow-up), so the caller says "check your connection" rather than
    #: implying the auditor read something it could not parse.
    audit_network: bool = False


def _vague(message: str) -> bool:
    return len(message.strip()) < VAGUE_LENGTH


def de_markdown(text: str) -> str:
    """Strip Markdown artifacts for terminal display.

    The prompts instruct plain text, but models occasionally emit Markdown
    anyway; this is the belt-and-braces pass. Bullets are captured first,
    then all asterisks, backticks, and double-underscore bolds are removed,
    '#' headers are flattened, blockquote markers are stripped, and pure
    horizontal-rule lines are dropped. Underscores are deliberately kept
    otherwise — stripping them would mangle identifiers like ``two_sum``.
    """
    lines = []
    for line in text.replace("**", "").replace("`", "").replace("__", "").splitlines():
        stripped = line.lstrip()
        if not stripped:
            lines.append(line)  # paragraph breaks survive
            continue
        if set(stripped) <= {"-", "*", "_", "="}:
            continue  # horizontal rules
        if stripped.startswith("#") and " " in stripped:
            header, _, rest = stripped.partition(" ")
            if set(header) == {"#"}:
                line = rest
        elif stripped.startswith("- ") or stripped.startswith("* "):
            line = "• " + stripped[2:]
        elif stripped.startswith(">"):
            line = stripped[1:].lstrip()
        lines.append(line)
    return "\n".join(lines).replace("*", "").rstrip().replace("\n\n\n", "\n\n")


def _tutor_call(backend: AIBackend, prompt: str, default_tier: int) -> tuple[str, int | None, str]:
    raw = backend.chat_json(Role.TUTOR, TUTOR_SYSTEM, prompt)
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


def _audit_once(backend: AIBackend, text: str) -> tuple[int | None, bool]:
    """One leak-audit call: ``(rating, offline)``.

    The rating is None when the audit cannot be read, and None means *unknown*,
    never "clean". A bare-int rating is accepted; a bool is not (it is an int in
    Python and would silently pass as a 1/0 score); a string or a missing key is
    unknown. The old version returned 1 — "clean" — for every one of those.

    An unreachable backend is one more way the audit cannot be read (v0.13
    follow-up), and it is reported as such: the hint call already answered, and
    losing that answer to a dropped connection should land on the *audit* path —
    "the check couldn't be read, so the answer was discarded" — instead of
    surfacing as the tutor failing to answer a question it did answer."""

    try:
        leak = backend.chat_json(Role.AUDITOR, LEAK_CHECK_SYSTEM, build_leak_prompt(text, 0))
    except Exception as exc:  # noqa: BLE001 - only connectivity is absorbed here
        if is_network_error(exc):
            return None, True
        raise  # a non-transport failure is a bug, and the guard reports it as one
    if not isinstance(leak, dict):
        return None, False
    rating = leak.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)):
        return None, False
    return int(rating), False


def _audit(backend: AIBackend, text: str) -> tuple[int | None, bool]:
    """Audit with a retry: a transient JSON hiccup in the auditor must not cost
    the student an answer, but a *persistent* one must not become a pass."""
    rating, offline = _audit_once(backend, text)
    attempts = 1
    while rating is None and not offline and attempts < AUDIT_ATTEMPTS:
        rating, offline = _audit_once(backend, text)
        attempts += 1  # retrying an unreachable backend just doubles the wait
    return rating, offline


def ask_tutor(
    backend: AIBackend,
    statement: str,
    code: str,
    tier: int,
    user_message: str,
    history: list[dict],
) -> HintResult:
    """Classify and answer, then leak-audit. A response still rated >= 3 after
    retries is discarded — never shown to the student. A response whose audit
    could not be read at all is discarded too, and says why (v0.13)."""
    vague = _vague(user_message)
    if vague:
        tier = 0
    prompt = build_tutor_prompt(statement, code, tier, user_message, history)
    kind, response_tier, text = _tutor_call(backend, prompt, default_tier=tier)
    if vague:
        kind = "ladder"  # "stuck" with no words is always the metacognition path

    rating, audit_network = _audit(backend, text)
    retries = 0
    while rating is not None and rating >= LEAK_THRESHOLD and retries < LEAK_RETRIES:
        flagged = (
            prompt
            + f"\n\nYour previous response was flagged as leaking too much of "
            f"the solution. Answer again more guardedly, keeping kind={kind}."
        )
        _, _, text = _tutor_call(backend, flagged, default_tier=tier)
        rating, audit_network = _audit(backend, text)
        retries += 1

    if rating is None:
        # Fail closed, and say which failure this is: the answer may be
        # perfectly good, but nothing verified that, and never-solve is the one
        # guarantee that cannot be delivered on trust.
        return HintResult(
            text="",
            tier=response_tier if kind == "ladder" else None,
            leak_rating=None,
            kind=kind,
            delivered=False,
            audit_failed=True,
            audit_network=audit_network,
        )
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
