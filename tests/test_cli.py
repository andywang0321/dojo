"""CLI user resolution: explicit --user, sole-user fallback, error cases."""

import pytest

from dojo.cli import _resolve_user
from dojo.db import get_or_create_user


def test_explicit_user_wins(db):
    get_or_create_user(db, "andy")
    get_or_create_user(db, "bea")
    assert _resolve_user(db, "andy") == "andy"


def test_sole_user_fallback(db):
    get_or_create_user(db, "andy")
    assert _resolve_user(db, None) == "andy"


def test_no_users_errors(db):
    with pytest.raises(RuntimeError, match="No users yet"):
        _resolve_user(db, None)


def test_multiple_users_errors(db):
    get_or_create_user(db, "andy")
    get_or_create_user(db, "bea")
    with pytest.raises(RuntimeError, match="Multiple users"):
        _resolve_user(db, None)
