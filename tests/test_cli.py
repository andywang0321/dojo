"""CLI: active-user resolution, user switching, argv normalization, seeding."""

import pytest

from dojo.bank import ensure_seeded
from dojo.cli import NeedsSetup, _active_user, _choose_user, _normalize_argv
from dojo.config import load_conf, save_conf
from dojo.db import get_or_create_user


# ------------------------------------------------------- active-user resolution


def test_conf_user_wins(db):
    get_or_create_user(db, "andy")
    get_or_create_user(db, "bea")
    assert _active_user(db, "bea") == "bea"


def test_conf_user_missing_errors(db):
    get_or_create_user(db, "andy")
    with pytest.raises(RuntimeError, match="configured user"):
        _active_user(db, "ghost")


def test_sole_user_fallback(db):
    get_or_create_user(db, "andy")
    assert _active_user(db, None) == "andy"


def test_no_users_raises_needs_setup(db):
    with pytest.raises(NeedsSetup):
        _active_user(db, None)


def test_multiple_users_raise_guidance(db):
    get_or_create_user(db, "andy")
    get_or_create_user(db, "bea")
    with pytest.raises(RuntimeError, match="dojo user"):
        _active_user(db, None)


# --------------------------------------------------------------- conf file


def test_conf_roundtrip(tmp_path):
    conf = tmp_path / "dojo.conf"
    save_conf({"user": "andy"}, conf)
    assert load_conf(conf) == {"user": "andy"}


def test_load_conf_missing_file(tmp_path):
    assert load_conf(tmp_path / "nope.conf") == {}


# -------------------------------------------------------------- argv surface


def test_normalize_bare_and_slug():
    assert _normalize_argv([]) == ["day"]
    assert _normalize_argv(["valid_parentheses"]) == ["day", "valid_parentheses"]
    assert _normalize_argv(["day", "valid_parentheses"]) == ["day", "valid_parentheses"]
    assert _normalize_argv(["list"]) == ["list"]
    assert _normalize_argv(["--help"]) == ["--help"]
    assert _normalize_argv(["-h"]) == ["-h"]
    assert _normalize_argv(["fetch", "two-sum"]) == ["fetch", "two-sum"]
    assert _normalize_argv(["user", "andy"]) == ["user", "andy"]


# ------------------------------------------------------------- user picker


def test_choose_user_picker(fake_console):
    console = fake_console(["2"])
    assert _choose_user(console, ["andy", "bea"]) == "bea"


def test_choose_user_picker_retries_on_bad_input(fake_console):
    console = fake_console(["0", "2"])
    assert _choose_user(console, ["andy", "bea"]) == "bea"


def test_choose_user_picker_cancels(fake_console):
    console = fake_console(["q"])
    assert _choose_user(console, ["andy", "bea"]) is None


# ------------------------------------------------------------ auto-reseeding


def test_ensure_seeded_upserts_and_is_idempotent(tmp_path):
    from dojo.db import connect

    problems_dir = tmp_path / "problems"
    db_path = tmp_path / "dojo.db"
    (problems_dir / "stack").mkdir(parents=True)
    (problems_dir / "stack" / "p1.py").write_text('"""One [Easy]\n\nReturn 1.\n"""\n')
    assert ensure_seeded(db_path, problems_dir) == 1
    assert ensure_seeded(db_path, problems_dir) == 1  # idempotent
    (problems_dir / "stack" / "p2.py").write_text('"""Two [Easy]\n\nReturn 2.\n"""\n')
    assert ensure_seeded(db_path, problems_dir) == 2
    with connect(db_path) as conn:
        rows = conn.execute("SELECT slug FROM problems ORDER BY slug").fetchall()
    assert [r["slug"] for r in rows] == ["p1", "p2"]


# ------------------------------------------------------- status-line counts


def test_due_counts(db):
    from dojo import scheduler
    from dojo.db import now

    uid = get_or_create_user(db, "andy")
    due_now = scheduler.ensure_card(db, uid, "stack", due_immediately=True)
    scheduler.ensure_card(db, uid, "heap")  # first review due tomorrow-ish
    assert scheduler.due_now_count(db, uid) == 1
    assert scheduler.due_next_day_count(db, uid) >= 1
