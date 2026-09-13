"""Complexity canonicalization and the three-valued comparison.

The comparison used to be two-valued and *silent*: `O(n+m)`, `O(n*m)` and
`O(k)` were not in the canonical table, so they were dropped and a claim about
them could never disagree with anything. These tests pin the third state.
"""

from dojo.complexity import (
    AGREE,
    DISAGREE,
    INCOMPARABLE,
    compare,
    normalize,
    parse,
    variables,
)


def test_normalize_known_forms():
    assert normalize("n") == "O(n)"
    assert normalize("nlogn") == "O(n log n)"
    assert normalize("n log n") == "O(n log n)"
    assert normalize("N^2") == "O(n^2)"
    assert normalize("1") == "O(1)"
    assert normalize("log(n)") == "O(log n)"
    assert normalize("n**2") == "O(n^2)"


def test_normalize_is_commutative_and_associative():
    """Order must not matter: the AI writes these both ways."""
    assert normalize("n+m") == normalize("m+n")
    assert normalize("n*m") == normalize("m*n")
    assert normalize("n*m") == "O(m*n)"
    assert normalize("v*logn") == "O(v log n)"


def test_parse_from_free_text():
    assert parse("O(n) because one pass") == "O(n)"
    assert parse("I think it's O(n log n) due to sorting") == "O(n log n)"
    assert parse("linear, roughly") is None
    assert parse(None) is None
    assert parse("") is None


def test_variables():
    assert variables("O(n log n)") == frozenset({"n"})
    assert variables("O(n + m)") == frozenset({"m", "n"})
    assert variables("O(k)") == frozenset({"k"})
    assert variables("O(1)") == frozenset()


def test_agreement():
    assert compare("O(n)", "O(n)") == AGREE
    assert compare("O(nlogn)", "O(n log n)") == AGREE
    assert compare("O(n + m)", "O(m+n)") == AGREE
    assert compare("O(n*m)", "O(m * n)") == AGREE
    assert compare("less than O(n)", "O(n)") == AGREE  # the qualifier is dropped
    assert compare("O(N^2)", "O(n^2)") == AGREE


def test_disagreement_over_the_same_variables():
    assert compare("O(n)", "O(n^2)") == DISAGREE
    assert compare("O(n)", "O(n log n)") == DISAGREE
    assert compare("O(1)", "O(n)") == DISAGREE
    assert compare("O(n)", "O(log n)") == DISAGREE


def test_multi_parameter_claims_are_incomparable_not_silent():
    """The regression: `O(n+m)` claims produced *no* mismatch against a
    measured `O(n^2)`, because both sides fell outside the canonical table and
    unknown classes were skipped. Silence is not agreement."""
    assert compare("O(n+m)", "O(n^2)") == INCOMPARABLE
    assert compare("O(m*n)", "O(n)") == INCOMPARABLE
    assert compare("O(k)", "O(n)") == INCOMPARABLE
    assert compare("O(n)", None) == INCOMPARABLE
    assert compare(None, None) == INCOMPARABLE
    assert compare("O(number of edges)", "O(n)") == INCOMPARABLE


def test_a_bracket_absorbs_a_claim_it_contains():
    """A measured O(n)…O(n log n) must not redden a student who claimed either
    end of it — that is the whole point of exposing the bracket."""
    bracket = ("O(n)", "O(n log n)")
    assert compare("O(n log n)", "O(n)", b_bracket=bracket) == AGREE
    assert compare("O(n)", "O(n)", b_bracket=bracket) == AGREE
    assert compare("O(n^2)", "O(n)", b_bracket=bracket) == DISAGREE
    assert compare("O(n^2)", "O(n)", b_bracket=("O(n)", "O(n log n)")) == DISAGREE
