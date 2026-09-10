"""CLI: active-user resolution, user switching, argv normalization, seeding."""

import pytest

from dojo.bank import ensure_seeded
from dojo.cli import NeedsSetup, _active_user, _choose_user, _normalize_argv
from dojo.config import load_conf, save_conf
from dojo.db import get_or_create_user
from dojo.tutor.backend import MockBackend

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


# ----------------------------------------------------- shared picker + learn

def test_choose_picker_generic(fake_console):
    from dojo.cli import _choose

    assert _choose(fake_console(["2"]), "Topics", ["heap", "graph"]) == "graph"


def test_choose_picker_retries_and_cancels(fake_console):
    from dojo.cli import _choose

    assert _choose(fake_console(["0", "2"]), "Topics", ["heap", "graph"]) == "graph"
    assert _choose(fake_console(["q"]), "Topics", ["heap"]) is None


def test_learn_command_normalizes_and_dispatches(db, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dojo.cli import _cmd_learn

    calls = []
    monkeypatch.setattr(
        "dojo.session.run_learn",
        lambda conn, console, backend, user, pattern, handoff_slug=None: calls.append(
            (pattern, handoff_slug)
        )
        or {"practice": None},
    )
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.tutor.get_backend", lambda: MockBackend())

    assert _cmd_learn(SimpleNamespace(topic="binary search", _user="andy")) == 0
    assert calls == [("binary_search", None)]


def test_learn_command_topic_picker(db, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dojo.cli import _cmd_learn

    calls = []
    monkeypatch.setattr(
        "dojo.session.run_learn",
        lambda *args, **kwargs: calls.append(args) or {"practice": None},
    )
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.tutor.get_backend", lambda: MockBackend())
    answers = iter(["3"])
    monkeypatch.setattr("dojo.cli.make_prompt", lambda console: lambda text: next(answers))

    assert _cmd_learn(SimpleNamespace(topic=None, _user="andy")) == 0
    assert calls and calls[0][4] == "two_pointers"  # third entry of PATTERNS


def test_learn_command_typo_errors(db, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dojo.cli import _cmd_learn

    calls = []
    monkeypatch.setattr(
        "dojo.session.run_learn",
        lambda *args, **kwargs: calls.append(args) or {"practice": None},
    )
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.tutor.get_backend", lambda: MockBackend())

    assert _cmd_learn(SimpleNamespace(topic="heep", _user="andy")) == 1
    assert _cmd_learn(SimpleNamespace(topic="zzzqqq", _user="andy")) == 1
    assert calls == []


def test_learn_command_practice_handoff_runs_session(db, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dojo.cli import _cmd_learn

    day_calls = []
    monkeypatch.setattr(
        "dojo.session.run_learn",
        lambda *args, **kwargs: {"practice": "valid_parentheses"},
    )
    monkeypatch.setattr(
        "dojo.session.run_day",
        lambda conn, console, backend, slug, user, **kwargs: day_calls.append(slug)
        or "solved",
    )
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.tutor.get_backend", lambda: MockBackend())

    assert _cmd_learn(SimpleNamespace(topic="stack", _user="andy")) == 0
    assert day_calls == ["valid_parentheses"]


# --------------------------------------------------- the day loop (v0.8 glue)

def _seed_curated_problem(conn, slug="kth_largest", pattern="heap"):
    from dojo.db import dumps_json, now

    conn.execute(
        """
        INSERT INTO problems (slug, title, difficulty, pattern, statement,
            function_name, expected_time, expected_space, visible_tests, created_at)
        VALUES (?, ?, 'Easy', ?, 's', 'solve_it', 'O(n)', 'O(n)', ?, ?)
        """,
        (slug, f"T {slug}", pattern, dumps_json([{"args": [[1]], "expected": 1}]), now()),
    )
    conn.commit()
    return conn.execute("SELECT id FROM problems WHERE slug = ?", (slug,)).fetchone()["id"]


def _day_args(**kwargs):
    from types import SimpleNamespace

    base = {"slug": None, "skip_warmup": True, "open": False, "_user": "andy"}
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mock_day_session(monkeypatch, learn_result=None):
    """Patch run_learn/run_day/get_backend/DB_PATH for _cmd_day tests;
    returns (learn_calls, day_calls)."""
    from dojo.tutor.backend import MockBackend

    learn_calls, day_calls = [], []
    monkeypatch.setattr(
        "dojo.session.run_learn",
        lambda conn, console, backend, user, pattern, handoff_slug=None: learn_calls.append(
            (pattern, handoff_slug)
        )
        or (learn_result or {"practice": None}),
    )
    monkeypatch.setattr(
        "dojo.session.run_day",
        lambda conn, console, backend, slug, user, **kwargs: day_calls.append(slug)
        or "solved",
    )
    monkeypatch.setattr("dojo.tutor.get_backend", lambda: MockBackend())
    return learn_calls, day_calls


def test_day_proactive_offer_accepted_proceeds(db, monkeypatch, tmp_path):
    from dojo.cli import _cmd_day

    _seed_curated_problem(db)
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    learn_calls, day_calls = _mock_day_session(monkeypatch)
    answers = iter(["y"])
    monkeypatch.setattr("dojo.cli.make_prompt", lambda console: lambda text: next(answers))

    assert _cmd_day(_day_args()) == 0
    assert learn_calls == [("heap", "kth_largest")]
    assert day_calls == ["kth_largest"]  # the session proceeds either way


def test_day_proactive_offer_declined_skips_learn(db, monkeypatch, tmp_path):
    from dojo.cli import _cmd_day

    _seed_curated_problem(db)
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    learn_calls, day_calls = _mock_day_session(monkeypatch)
    answers = iter(["n"])
    monkeypatch.setattr("dojo.cli.make_prompt", lambda console: lambda text: next(answers))

    assert _cmd_day(_day_args()) == 0
    assert learn_calls == []
    assert day_calls == ["kth_largest"]


def test_day_studied_pattern_never_offers(db, monkeypatch, tmp_path):
    """Any attempt in the pattern makes it studied — the offer must not even
    prompt (the empty answer queue would raise if it did)."""
    from dojo.cli import _cmd_day

    pid = _seed_curated_problem(db)
    uid = get_or_create_user(db, "andy")
    from dojo.db import now

    db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at) "
        "VALUES (?, ?, 'solve', 'unsolved', ?)",
        (uid, pid, now()),
    )
    db.commit()
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    learn_calls, day_calls = _mock_day_session(monkeypatch)
    monkeypatch.setattr(
        "dojo.cli.make_prompt",
        lambda console: lambda text: (_ for _ in ()).throw(StopIteration()),
    )

    assert _cmd_day(_day_args()) == 0
    assert learn_calls == []
    assert day_calls == ["kth_largest"]


def test_day_explicit_slug_never_offers(db, monkeypatch, tmp_path):
    """Explicit slugs are deliberate choices — the proactive offer is for
    scheduler picks only."""
    from dojo.cli import _cmd_day

    _seed_curated_problem(db)
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    learn_calls, day_calls = _mock_day_session(monkeypatch)
    monkeypatch.setattr(
        "dojo.cli.make_prompt",
        lambda console: lambda text: (_ for _ in ()).throw(StopIteration()),
    )

    assert _cmd_day(_day_args(slug="kth_largest")) == 0
    assert learn_calls == []
    assert day_calls == ["kth_largest"]


def test_day_practice_outcome_loops_on_same_slug(db, monkeypatch, tmp_path):
    """The in-session learn handoff returns 'practice'; _cmd_day loops back
    into a fresh session on the same slug."""
    from dojo.cli import _cmd_day

    _seed_curated_problem(db)
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    _, day_calls = _mock_day_session(monkeypatch)
    answers = iter(["n"])
    monkeypatch.setattr("dojo.cli.make_prompt", lambda console: lambda text: next(answers))
    outcomes = iter(["practice", "solved"])
    monkeypatch.setattr(
        "dojo.session.run_day",
        lambda conn, console, backend, slug, user, **kwargs: day_calls.append(slug)
        or next(outcomes),
    )

    assert _cmd_day(_day_args()) == 0
    assert day_calls == ["kth_largest", "kth_largest"]
