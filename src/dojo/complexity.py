"""Complexity-string normalization.

Both humans and the AI tutor/reviewer speak complexity loosely ("O(n)",
"o(n log n)", "O(N^2)", "O(nlogn)"). Everything in dojo compares classes as
canonical strings, so claims, expectations, and measurements can be checked
against each other mechanically.
"""

from __future__ import annotations

import re

_CANONICAL = {
    "1": "O(1)",
    "logn": "O(log n)",
    "log(n)": "O(log n)",
    "n": "O(n)",
    "nlogn": "O(n log n)",
    "nlog(n)": "O(n log n)",
    "n*logn": "O(n log n)",
    "n^2": "O(n^2)",
    "n2": "O(n^2)",
    "n^3": "O(n^3)",
    "n3": "O(n^3)",
    "2^n": "O(2^n)",
    "n!": "O(n!)",
}

KNOWN_CLASSES = sorted(set(_CANONICAL.values()))

_COMPLEX_RE = re.compile(r"O\s*\(\s*([^)]*)\s*\)", re.IGNORECASE)


def normalize(inner: str) -> str:
    """Normalize the *inside* of an O(...) to a canonical class string."""
    cleaned = (
        inner.strip()
        .lower()
        .replace("²", "^2")
        .replace(" ", "")
        .replace("*", "")
    )
    return _CANONICAL.get(cleaned, f"O({inner.strip()})")


def parse(raw: str | None) -> str | None:
    """Extract and normalize the first O(...) from free text, else None."""
    if not raw:
        return None
    match = _COMPLEX_RE.search(raw)
    if not match:
        return None
    return normalize(match.group(1))


def mismatch(*classes: str | None) -> bool:
    """True if any two known classes differ. Unknown classes are skipped
    (never fabricate a disagreement the data can't support)."""
    known = [c for c in classes if c in KNOWN_CLASSES]
    return len(set(known)) > 1
