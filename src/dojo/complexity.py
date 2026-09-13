"""Complexity-string normalization and comparison.

Both humans and the AI speak complexity loosely ("O(n)", "o(n log n)",
"O(N^2)", "O(nlogn)", "O(n + m)"). Everything dojo compares goes through one
canonicalization first, so claims, expectations and measurements can be
checked against each other mechanically.

The comparison is **three-valued** (v0.11):

- ``AGREE``   — the two expressions denote the same class;
- ``DISAGREE`` — different classes over the same size variables;
- ``INCOMPARABLE`` — they are not about the same thing.

The third state exists because the previous two-valued version silently
dropped anything it did not recognize. ``O(n+m)``, ``O(n*m)`` and ``O(k)``
were absent from the canonical table, so comparing a student's ``O(n+m)``
claim against a measured ``O(n^2)`` returned "no mismatch": the three-way
table showed a confident blank where the widest disagreement in the book
should have been. Unrecognized is not the same as agreeing, and the table now
says which it is.

Internally a class is a set of *terms*, each term a sorted set of factors, so
commutativity and associativity stop mattering: ``O(n + m)``, ``O(m+n)`` and
``O(n+m)`` are one class, and so are ``O(n*m)`` and ``O(m*n)``. Display uses
the spelling the rest of dojo already uses (``O(n log n)``).
"""

from __future__ import annotations

import re

#: The classes the profiler can emit: one variable (n), one term. Anything
#: else is a claim about a parameter the measurement protocol does not scale.
KNOWN_CLASSES = (
    "O(1)",
    "O(log n)",
    "O(n)",
    "O(n log n)",
    "O(n^2)",
    "O(n^3)",
    "O(2^n)",
    "O(n!)",
)

#: Longest first: an implicit product like "nlogn" is split by consuming these
#: tokens greedily, so "n" must not match before "n^2".
_FACTORS = ("2^n", "n^3", "n^2", "n!", "logn", "log(n)", "log", "n", "m", "k", "v", "e", "1")

#: Whole-term spellings that must not be re-split ("n2" is n^2, not n·2).
_TERM_ALIASES = {
    "n2": "n^2",
    "n3": "n^3",
    "n^2": "n^2",
    "n^3": "n^3",
    "nlogn": "n*logn",
    "nlog(n)": "n*logn",
    "1": "1",
    "logn": "logn",
    "log(n)": "logn",
    "n!": "n!",
    "2^n": "2^n",
}

_FACTOR_CANON = {"log": "logn", "log(n)": "logn"}

_COMPLEX_RE = re.compile(r"O\s*\(\s*([^)]*)\s*\)", re.IGNORECASE)
_LETTERS_RE = re.compile(r"[a-z]+")

AGREE = "agree"
DISAGREE = "disagree"
INCOMPARABLE = "incomparable"


def _inner(class_str: str) -> str:
    match = _COMPLEX_RE.search(class_str)
    return match.group(1) if match else class_str


def _split_factors(term: str) -> list[str]:
    if "*" in term:
        return [p for p in term.split("*") if p]
    factors, rest = [], term
    while rest:
        for token in _FACTORS:
            if rest.startswith(token):
                factors.append(token)
                rest = rest[len(token) :]
                break
        else:  # unknown chunk: keep it whole rather than guess
            factors.append(rest)
            rest = ""
    return factors


def _canon_term(term: str) -> str:
    term = term.strip()
    if term in _TERM_ALIASES:
        term = _TERM_ALIASES[term]
    factors = _split_factors(term)
    if any(f not in _FACTORS for f in factors):
        return term  # unknown shape: keep it whole rather than invent a product
    # `log n` reads as a modifier, so it sorts last: "n log n", not "log n*n".
    ordered = sorted((_FACTOR_CANON.get(f, f) for f in factors), key=lambda f: (f == "logn", f))
    return "*".join(ordered)


def _terms(class_str: str) -> frozenset[str]:
    """The canonical term set: {"n*logn"} for O(n log n), {"m","n"} for O(n+m)."""
    cleaned = _inner(class_str).strip().lower().replace("²", "^2")
    cleaned = cleaned.replace("**", "^").replace(" ", "")
    terms = {_canon_term(part) for part in cleaned.split("+") if part}
    return frozenset(t for t in terms if t)


def _render(terms: frozenset[str]) -> str:
    """Pretty spelling: factors joined by '*', except that a `log n` factor
    sits next to its neighbour separated by a space ("n log n")."""
    def pretty_factor(factor: str) -> str:
        return "log n" if factor == "logn" else factor

    rendered = []
    for term in sorted(terms):
        factors = term.split("*")
        pretty = pretty_factor(factors[0])
        for factor in factors[1:]:
            pretty += (" " if factor == "logn" else "*") + pretty_factor(factor)
        rendered.append(pretty)
    return "O(" + " + ".join(rendered) + ")"


def normalize(inner: str) -> str:
    """Normalize the *inside* of an O(...) to a canonical class string."""
    terms = _terms(inner)
    return _render(terms) if terms else f"O({inner.strip()})"


def parse(raw: str | None) -> str | None:
    """Extract and normalize the first O(...) from free text, else None."""
    if not raw:
        return None
    if not _COMPLEX_RE.search(raw):
        return None
    return normalize(raw)


def variables(class_str: str | None) -> frozenset[str]:
    """The size variables a class is expressed in: {n} for O(n log n), {m, n}
    for O(n+m), empty for O(1)."""
    if not class_str:
        return frozenset()
    # `log n` is a factor, not a variable: pad it so letter runs split there.
    inner = _inner(class_str).lower().replace(" ", "").replace("logn", " l ")
    return frozenset(_LETTERS_RE.findall(inner)) - {"l"}


def _comparable(va: frozenset[str], vb: frozenset[str]) -> bool:
    """False when one side brings a size variable the other does not have —
    the measurement scales a single parameter, so O(n) says nothing about a
    claim in m or k."""
    if va == vb:
        return True
    return va <= {"n"} and vb <= {"n"}


def compare(
    a: str | None, b: str | None, *, b_bracket: tuple[str, ...] | None = None
) -> str:
    """Compare two classes, given raw text or canonical strings.

    ``b_bracket`` is the measured side's plausible set: a claim the
    measurement cannot rule out is not a disagreement — that is what makes a
    bracketed ``O(n)…O(n log n)`` harmless for a student who claimed either
    end of it."""
    if a is None or b is None:
        return INCOMPARABLE
    terms_a, terms_b = _terms(a), _terms(b)
    if terms_a == terms_b:
        return AGREE
    if b_bracket and any(_terms(a) == _terms(c) for c in b_bracket):
        return AGREE
    if not _comparable(variables(a), variables(b)):
        return INCOMPARABLE
    return DISAGREE
