"""Complexity-string normalization and mismatch detection."""

from dojo.complexity import mismatch, normalize, parse


def test_normalize_known_forms():
    assert normalize("n") == "O(n)"
    assert normalize("nlogn") == "O(n log n)"
    assert normalize("n log n") == "O(n log n)"
    assert normalize("N^2") == "O(n^2)"
    assert normalize("1") == "O(1)"
    assert normalize("log(n)") == "O(log n)"


def test_parse_from_free_text():
    assert parse("O(n) because one pass") == "O(n)"
    assert parse("I think it's O(n log n) due to sorting") == "O(n log n)"
    assert parse("linear, roughly") is None
    assert parse(None) is None
    assert parse("") is None


def test_mismatch_logic():
    assert mismatch("O(n)", "O(n^2)")
    assert not mismatch("O(n)", "O(n)")
    assert not mismatch("O(n)", None)  # unknown values never fabricate a diff
    assert mismatch("O(n)", "O(weird)", "O(n^2)")  # unknown skipped, known pair differs
