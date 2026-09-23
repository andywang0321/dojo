"""CLI: active-user resolution, user switching, argv normalization, seeding."""

import json

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

    uid = get_or_create_user(db, "andy")
    due_now = scheduler.ensure_item_card(db, uid, "valid_parentheses", "stack", due_immediately=True)
    soon = scheduler.ensure_item_card(db, uid, "k_closest_points", "heap")
    # A freshly seeded "good" card is days out, not hours (v0.11), so pin the
    # 24-hour window explicitly instead of relying on the seeding policy. Written
    # in SQLite's *naive* format on purpose: the counts must be format-agnostic
    # (see test_scheduler.test_due_comparisons_survive_a_naive_timestamp).
    db.execute(
        "UPDATE item_cards SET due_at = datetime('now', '+6 hours') WHERE id = ?",
        (soon["id"],),
    )
    db.commit()
    later = scheduler.ensure_item_card(db, uid, "two_sum", "trees")  # days out: in neither count
    assert scheduler.due_now_count(db, uid) == 1
    assert scheduler.due_next_day_count(db, uid) == 1
    assert later["due_at"] > scheduler.now()


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
    answers = iter(["2"])
    monkeypatch.setattr("dojo.cli.make_prompt", lambda console: lambda text: next(answers))

    assert _cmd_learn(SimpleNamespace(topic=None, _user="andy")) == 0
    assert calls and calls[0][4] == "two_pointers"  # second entry of PATTERNS


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


# ------------------------------------------------------------ help surface (v0.9)

def test_help_variants_show_minimal_guide(capsys):
    """`dojo help`, `dojo -h`, and `dojo --help` all print the same minimal
    guide: the everyday commands, none of the power tools."""
    from dojo.cli import main

    for argv in (["--help"], ["-h"], ["help"], ["--help", "extra"]):
        assert main(argv) == 0
        out = capsys.readouterr().out
        assert "learn [TOPIC]" in out
        assert "roadmap" in out
        assert "history" in out
        assert "uv run dojo" in out  # the first-run pointer
        for hidden in ("dojo day", "dojo warmup", "dojo check", "dojo report", "dojo curate"):
            assert hidden not in out


def test_hidden_commands_still_dispatch():
    """Hidden from the guide ≠ deleted: `profile` is history's alias, and
    `show`/`day`/`report` keep working for muscle memory and in-session
    pointers (they document themselves via `dojo <cmd> --help`)."""
    from dojo.cli import PARSER, _cmd_history

    assert PARSER.parse_args(["profile"]).func is _cmd_history
    args = PARSER.parse_args(["show", "3"])
    assert args.command == "show" and args.attempt_id == 3
    assert PARSER.parse_args(["day", "two_sum"]).command == "day"
    assert PARSER.parse_args(["report", "--fix", "two_sum"]).command == "report"


# ----------------------------------------------------------- roadmap (v0.10)

def _seed_ladder(conn, slug, pattern, lc):
    from dojo.db import dumps_json, now

    conn.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
        "function_name, visible_tests, lc_number, created_at) "
        "VALUES (?, ?, 'Easy', ?, 's', 'fn', ?, ?, ?)",
        (slug, slug, pattern, dumps_json([{"args": [[]], "expected": None}]), lc, now()),
    )
    conn.commit()


def _solve_slug(conn, user_id, slug):
    from dojo.db import now

    pid = conn.execute("SELECT id FROM problems WHERE slug = ?", (slug,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', ?, ?)",
        (user_id, pid, now(), now()),
    )
    conn.commit()


def test_roadmap_rows_gate_state(db):
    """The roadmap view's data: ladder counts, complete/next-up markers,
    and the hard prereq gate's locked-by attribution."""
    from dojo.cli import _roadmap_rows

    uid = get_or_create_user(db, "andy")
    _seed_ladder(db, "two_sum", "arrays_and_hashing", 1)
    _seed_ladder(db, "group_anagrams", "arrays_and_hashing", 49)
    _seed_ladder(db, "valid_palindrome", "two_pointers", 125)
    _solve_slug(db, uid, "two_sum")

    rows, next_pick = _roadmap_rows(db, uid)
    arrays = rows[0]
    assert arrays["available"] == 2 and arrays["solved"] == 1
    assert arrays["complete"] is False and arrays["next_up"] is True
    assert arrays["locked_by"] is None
    two_ptrs = rows[1]
    assert two_ptrs["locked_by"] == "arrays_and_hashing"
    assert two_ptrs["next_up"] is False
    assert next_pick["slug"] == "group_anagrams"

    _solve_slug(db, uid, "group_anagrams")  # arrays ladder complete
    rows, next_pick = _roadmap_rows(db, uid)
    assert rows[0]["complete"] is True and rows[0]["next_up"] is False
    assert rows[1]["next_up"] is True and rows[1]["locked_by"] is None
    assert next_pick["slug"] == "valid_palindrome"


def test_roadmap_command_dispatches(db, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dojo.cli import _cmd_roadmap

    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    args = SimpleNamespace(_user="andy", table=False, expand=None, all=False)
    assert _cmd_roadmap(args) == 0


def test_roadmap_tree_data_states(db):
    """Per-problem ladder states: solved / next / ready / missing, and the
    group rows carry the gate fields."""
    from dojo.cli import _roadmap_tree

    uid = get_or_create_user(db, "andy")
    _seed_ladder(db, "two_sum", "arrays_and_hashing", 1)
    _seed_ladder(db, "group_anagrams", "arrays_and_hashing", 49)
    _seed_ladder(db, "valid_palindrome", "two_pointers", 125)
    _solve_slug(db, uid, "two_sum")

    entries, next_pick = _roadmap_tree(db, uid)
    arrays = entries[0]
    states = {p["lc"]: p["state"] for p in arrays["problems"]}
    assert states[1] == "solved"
    assert states[49] == "next"  # the ladder's earliest unsolved in the group
    assert states[217] == "missing"  # on the ladder, not fetched
    assert arrays["next_up"] is True
    two_ptrs = entries[1]
    assert two_ptrs["locked_by"] == "arrays_and_hashing"
    assert next_pick["slug"] == "group_anagrams"


def _render_roadmap(**kwargs):
    from rich.console import Console

    from dojo.cli import _cmd_roadmap

    console = Console(
        force_terminal=True, color_system="standard", width=160, no_color=False
    )
    with console.capture() as cap:
        # _cmd_roadmap builds its own Console; capture the tree via the
        # renderer directly instead.
        from dojo.cli import _render_roadmap_tree

        _render_roadmap_tree(console, kwargs.pop("entries"), kwargs.pop("next_pick"), **kwargs)
    return cap.get()


def test_roadmap_tree_renders_branches_and_expansion(db):
    from dojo.cli import _roadmap_tree

    uid = get_or_create_user(db, "andy")
    _seed_ladder(db, "two_sum", "arrays_and_hashing", 1)
    _seed_ladder(db, "group_anagrams", "arrays_and_hashing", 49)
    _seed_ladder(db, "valid_palindrome", "two_pointers", 125)
    _solve_slug(db, uid, "two_sum")

    entries, next_pick = _roadmap_tree(db, uid)
    out = _render_roadmap(entries=entries, next_pick=next_pick)
    assert "NeetCode 150" in out
    assert "├──" in out  # tree branches
    assert "← next up" in out
    assert "group_anagrams" in out  # the expanded next-up group's ladder
    assert "valid_palindrome" not in out  # collapsed groups stay one line

    out = _render_roadmap(entries=entries, next_pick=next_pick, expand_all=True)
    assert "valid_palindrome" in out  # --all expands everything


# ------------------------------------------------- attempt detail (v0.11)


def test_show_displays_the_recall_grade(db, tmp_path, monkeypatch, capsys):
    """v0.11: the warm-up recall grade is persisted on the attempt row, so
    `dojo show` surfaces it. It used to be folded into the card aggregates and
    discarded, which made per-pattern recall curves unreconstructible."""
    import argparse

    from dojo.cli import _cmd_show
    from dojo.db import now

    pid = _seed_curated_problem(db)
    uid = get_or_create_user(db, "andy")
    cur = db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, "
        "submitted_at, recall_grade) VALUES (?, ?, 'warmup', 'correct', ?, ?, 2)",
        (uid, pid, now(), now()),
    )
    db.commit()

    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    args = argparse.Namespace(attempt_id=cur.lastrowid, code=False)

    assert _cmd_show(args) == 0
    # rich wraps the status line at the captured console width; collapse
    # whitespace so the assertion does not depend on where the wrap landed.
    assert "recall grade: 2" in " ".join(capsys.readouterr().out.split())


def test_show_omits_the_grade_for_a_solve(db, tmp_path, monkeypatch, capsys):
    import argparse

    from dojo.cli import _cmd_show
    from dojo.db import now

    pid = _seed_curated_problem(db)
    uid = get_or_create_user(db, "andy")
    cur = db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', ?, ?)",
        (uid, pid, now(), now()),
    )
    db.commit()

    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    args = argparse.Namespace(attempt_id=cur.lastrowid, code=False)

    assert _cmd_show(args) == 0
    assert "recall grade" not in " ".join(capsys.readouterr().out.split())


# ------------------------------------- product-level smoke tests (v0.13)
# The suite tested functions, not the product: 10 of 17 `_cmd_*` handlers had no
# caller and `main()` appeared once, with help argv. These drive the real entry
# point against a temp DB and workbench (the `cli_env` fixture), so argument
# normalization, user resolution, seeding, and dispatch are exercised together.


def _seed_user(db_path, name="andy"):
    from dojo.db import connect, get_or_create_user

    conn = connect(db_path)
    uid = get_or_create_user(conn, name)
    conn.close()
    return uid


def test_main_list_runs_end_to_end(cli_env):
    """`dojo list` through main(): seeds the bank, resolves the sole user, and
    renders the table — the whole dispatch chain the suite never touched."""
    from dojo.cli import main

    rec, db_path, _workbench, _problems = cli_env
    _seed_user(db_path)
    assert main(["list"]) == 0
    assert "Problem bank" in rec.text
    assert "valid_parentheses" in rec.text


def test_main_history_and_show_run_end_to_end(cli_env):
    from dojo.cli import main

    rec, db_path, _workbench, _problems = cli_env
    _seed_user(db_path)
    assert main(["history"]) == 0
    assert "Attempts" in rec.text
    # No attempt 999: the command must fail loudly, not silently.
    assert main(["show", "999"]) == 1
    assert "No attempt with id 999" in rec.text


def test_main_day_writes_a_template_and_quit_records_nothing(cli_env):
    """The daily entry point, end to end, with the mock backend and a canned
    `quit`: the template lands in the *temp* workbench, and the v0.11 lifecycle
    rule holds through the real CLI (quit writes no attempt row)."""
    from dojo.cli import main
    from dojo.db import connect

    rec, db_path, workbench, _problems = cli_env
    _seed_user(db_path)
    rec.answers = ["quit"]

    assert main(["day", "valid_parentheses"]) == 0
    assert (workbench / "valid_parentheses.py").exists()
    assert "def is_valid" in (workbench / "valid_parentheses.py").read_text()

    conn = connect(db_path)
    rows = conn.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"]
    conn.close()
    assert rows == 0, "quit must record nothing (v0.11 lifecycle)"


def test_main_unknown_slug_is_a_clean_failure(cli_env):
    from dojo.cli import main

    rec, db_path, _workbench, _problems = cli_env
    _seed_user(db_path)
    assert main(["day", "no_such_problem_xyz"]) == 1
    assert "Unknown problem" in rec.text


def test_main_check_without_a_session_points_at_day(cli_env):
    from dojo.cli import main

    rec, db_path, _workbench, _problems = cli_env
    _seed_user(db_path)
    assert main(["check"]) == 1
    assert "No active session" in rec.text


def test_active_state_slug_prefers_the_most_recent_session(tmp_path, monkeypatch):
    """Two crashed sessions used to mean `dojo check` tested whichever slug
    sorted first (which is how a session killed mid-solve could silently be
    checked against the wrong problem). The most recently used one wins."""
    import os
    import time

    from dojo.cli import _active_state_slug

    workbench = tmp_path / "wb"
    workbench.mkdir()
    older = workbench / "aaa_old.state.json"
    newer = workbench / "zzz_new.state.json"
    older.write_text("{}")
    newer.write_text("{}")
    os.utime(older, (time.time() - 600, time.time() - 600))
    monkeypatch.setattr("dojo.cli.WORKBENCH_DIR", workbench)

    printed: list[str] = []

    class C:
        def print(self, *a, **k):
            printed.append(" ".join(str(x) for x in a))

    assert _active_state_slug(C()) == "zzz_new"
    assert "zzz_new" in " ".join(printed)  # the guess is never invisible


def test_show_clean_strips_dojos_scaffolding(db, tmp_path, monkeypatch, capsys):
    """`dojo show --code` keeps the raw artifact (the truth of what ran);
    `--clean` shows what the AI actually read (v0.13)."""
    import argparse

    from dojo.cli import _cmd_show
    from dojo.db import now
    from dojo.session import workbench as wb

    pid = _seed_curated_problem(db)
    uid = get_or_create_user(db, "andy")
    problem = db.execute("SELECT * FROM problems WHERE id = ?", (pid,)).fetchone()
    solved = wb.template_for(problem).replace(
        "    raise NotImplementedError", "    return 1"
    )
    cur = db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at, code) "
        "VALUES (?, ?, 'solve', 'correct', ?, ?, ?)",
        (uid, pid, now(), now(), solved),
    )
    db.commit()
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")

    assert _cmd_show(argparse.Namespace(attempt_id=cur.lastrowid, code=True, clean=False)) == 0
    raw = capsys.readouterr().out
    assert raw.startswith("#!")                      # the raw artifact

    assert _cmd_show(argparse.Namespace(attempt_id=cur.lastrowid, code=False, clean=True)) == 0
    clean = capsys.readouterr().out
    assert not clean.startswith("#!")
    assert wb.SENTINEL_OPEN not in clean
    assert "return 1" in clean


def test_show_revisions_and_diff_render(db, tmp_path, monkeypatch, capsys):
    """The point of storing revisions is being able to *see* what changed —
    `--revisions` lists them, `--diff` shows the delta."""
    import argparse

    from dojo.cli import _cmd_show
    from dojo.db import insert_revision, now

    pid = _seed_curated_problem(db)
    uid = get_or_create_user(db, "andy")
    cur = db.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at, code) "
        "VALUES (?, ?, 'solve', 'correct', ?, ?, ?)",
        (uid, pid, now(), now(), "def solve_it(*args, **kwargs):\n    return 1\n"),
    )
    attempt_id = cur.lastrowid
    insert_revision(db, attempt_id, kind="submit", code="a = 1\nb = 2\n", status="wrong_answer")
    insert_revision(db, attempt_id, kind="polish", code="a = 1\nb = 3\n", status="correct")
    db.commit()
    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")

    assert _cmd_show(argparse.Namespace(attempt_id=attempt_id, code=False, clean=False,
                                        revisions=True, rev=None, diff=None)) == 0
    listing = capsys.readouterr().out
    assert "Revisions" in listing and "polish" in listing

    assert _cmd_show(argparse.Namespace(attempt_id=attempt_id, code=False, clean=False,
                                        revisions=False, rev=1, diff=None)) == 0
    one = capsys.readouterr().out
    assert "b = 2" in one and "revision 1 of" in one

    assert _cmd_show(argparse.Namespace(attempt_id=attempt_id, code=False, clean=False,
                                        revisions=False, rev=None, diff=[])) == 0
    delta = capsys.readouterr().out
    assert "-b = 2" in delta and "+b = 3" in delta


def test_input_ending_at_a_prompt_stops_cleanly(cli_env, capsys):
    """Ctrl-D (or a piped script running out of lines) used to surface as an
    `EOFError` traceback out of `rich.Console.input`. The state file stays, so
    the same command resumes the session."""
    import unittest.mock as mock

    from rich.console import Console

    from dojo.cli import main

    _rec, db_path, workbench, _problems = cli_env
    _seed_user(db_path)

    def eof_input(self, prompt="", **kwargs):  # noqa: ANN001
        raise EOFError

    with mock.patch.object(Console, "input", eof_input):
        assert main(["day", "valid_parentheses"]) == 1

    assert "Input ended" in capsys.readouterr().out
    assert list(workbench.glob("*.state.json")), "the session must remain resumable"


def test_the_footer_names_when_the_next_warm_up_arrives(cli_env):
    """End to end: a card due in 13 hours makes the footer say so — the old line
    ("tomorrow: 1 card(s) due") sent a real user looking for a warm-up that was
    not due until late that night."""
    from datetime import datetime, timedelta, timezone

    from dojo.cli import main
    from dojo.db import connect, now

    rec, db_path, _workbench, _problems = cli_env
    uid = _seed_user(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO item_cards (user_id, slug, pattern, stability, difficulty, reps, "
        "lapses, due_at, created_at) VALUES (?, 'valid_parentheses', 'stack', 1.0, 5.0, 0, 0, ?, ?)",
        (uid, (datetime.now(timezone.utc) + timedelta(hours=13)).isoformat(timespec="seconds"), now()),
    )
    conn.commit()
    conn.close()

    assert main(["list"]) == 0  # a non-session command, so no session runs
    rec.out.clear()
    assert main(["day", "valid_parentheses"]) == 0  # then a full session, all `quit`
    assert "next warm-up" in rec.text
    assert "tomorrow:" not in rec.text


def test_progress_counts_due_cards_the_way_the_scheduler_does(db, tmp_path, monkeypatch, capsys):
    """`dojo progress` compared `due_at <= now()` as *strings* while the
    scheduler normalized with `datetime()`. A row written by SQLite's own naive
    `datetime('now')` form sorts before the ISO form, so the table said "due now"
    for a card the scheduler would not serve (v0.13 audit, S2.15)."""
    from datetime import datetime, timedelta, timezone

    from dojo.cli import _cmd_progress
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    naive_future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO item_cards (user_id, slug, pattern, stability, difficulty, reps, "
        "lapses, due_at, created_at) VALUES (?, 'valid_parentheses', 'stack', 1.0, 5.0, 0, 0, ?, ?)",
        (uid, naive_future, naive_future),
    )
    db.commit()

    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.cli.load_conf", lambda *a, **k: {"user": "andy"})
    import argparse

    assert _cmd_progress(argparse.Namespace(_user="andy")) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "stack" in out
    # The card is five days out, so the "due now" column must read 0 — the raw
    # string compare read it as due.
    row = out[out.index("stack"):]
    assert " 0 " in row[:40], row[:80]


# ---------------------------------- per-problem cards (v0.13 follow-up)


def test_warmup_limit_drains_the_backlog_and_says_what_is_left(cli_env):
    """Per-problem cards mean several can be due at once, so the drain is
    explicit: `--limit N`, and a line saying how many are still waiting."""
    from dojo import scheduler
    from dojo.cli import main
    from dojo.db import connect, now

    rec, db_path, _workbench, _problems = cli_env
    uid = _seed_user(db_path)
    conn = connect(db_path)
    for i in range(4):
        db_problem = f"backlog_{i}"
        conn.execute(
            "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
            "function_name, visible_tests, signature, created_at) VALUES "
            "(?, ?, 'Easy', 'stack', 's', 'solve_it', ?, ?, ?)",
            (db_problem, db_problem.upper(),
             json.dumps([{"args": [[1]], "expected": 1}]),
             json.dumps("(nums: list[int]) -> int"), now()),
        )
        scheduler.ensure_item_card(conn, uid, db_problem, "stack", due_immediately=True)
    conn.commit()
    conn.close()

    # `--limit 1` serves one card; quitting it records nothing (v0.11), so the
    # card is *still* due and the line says so. What matters here is that the
    # limit is honoured and the backlog is never invisible.
    rec.answers = ["quit"]
    assert main(["warmup", "--limit", "1"]) == 0
    assert "Warm-up: 1 card(s) due" in rec.text
    assert "4 more card(s) still due" in rec.text
    assert "--limit 4" in rec.text


def test_the_one_time_card_migration_runs_and_says_so(cli_env):
    """A DB with legacy pattern cards and no item cards is upgraded once, from
    the attempt log, with one line explaining what happened."""
    from dojo.cli import main
    from dojo.db import connect, dumps_json, now

    rec, db_path, _workbench, _problems = cli_env
    uid = _seed_user(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
        "function_name, visible_tests, signature, created_at) VALUES "
        "('legacy_solved', 'L', 'Easy', 'stack', 's', 'solve_it', ?, ?, ?)",
        (dumps_json([{"args": [[1]], "expected": 1}]),
         dumps_json("(nums: list[int]) -> int"), now()),
    )
    conn.commit()
    pid = conn.execute("SELECT id FROM problems").fetchone()["id"]
    conn.execute(
        "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, submitted_at) "
        "VALUES (?, ?, 'solve', 'correct', ?, ?)",
        (uid, pid, now(), now()),
    )
    # The legacy card the old model would have left behind.
    conn.execute(
        "INSERT INTO pattern_cards (user_id, pattern, stability, difficulty, reps, "
        "lapses, due_at, created_at) VALUES (?, 'stack', 12.0, 5.0, 3, 0, ?, ?)",
        (uid, now(), now()),
    )
    conn.commit()
    conn.close()

    assert main(["progress"]) == 0
    assert "Cards are per problem now" in rec.text
    assert "rebuilt 1" in rec.text.replace("  ", " ")

    conn = connect(db_path)
    cards = conn.execute("SELECT slug FROM item_cards").fetchall()
    conn.close()
    assert [c["slug"] for c in cards] == ["legacy_solved"]


def test_progress_problems_lists_every_card_coldest_first(db, tmp_path, monkeypatch, capsys):
    """`dojo progress --problems` is the per-problem view the pattern rollup
    cannot give: which specific problems are cold."""
    import argparse

    from dojo import scheduler
    from dojo.cli import _cmd_progress
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    scheduler.ensure_item_card(db, uid, "hot_problem", "stack", due_immediately=True)
    cold = scheduler.ensure_item_card(db, uid, "cold_problem", "stack")
    db.execute(
        "UPDATE item_cards SET due_at = datetime('now', '+30 days') WHERE id = ?",
        (cold["id"],),
    )
    db.commit()

    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.cli.load_conf", lambda *a, **k: {"user": "andy"})
    assert _cmd_progress(argparse.Namespace(_user="andy", problems=True)) == 0
    out = capsys.readouterr().out
    assert "Cards — andy" in out
    assert "hot_problem" in out and "cold_problem" in out
    assert out.index("hot_problem") < out.index("cold_problem")  # coldest due first
    assert "next review" in out


def test_the_pattern_table_reports_the_weakest_card(db, tmp_path, monkeypatch, capsys):
    """A pattern's mean stability can look healthy while one problem is cold;
    the `weakest` column is the honest signal with per-problem cards."""
    import argparse

    from dojo import scheduler
    from dojo.cli import _cmd_progress
    from dojo.db import get_or_create_user

    uid = get_or_create_user(db, "andy")
    strong = scheduler.ensure_item_card(db, uid, "strong_problem", "stack")
    db.execute("UPDATE item_cards SET stability = 90.0 WHERE id = ?", (strong["id"],))
    db.commit()
    weak = scheduler.ensure_item_card(db, uid, "weak_problem", "stack")
    db.execute("UPDATE item_cards SET stability = 1.0 WHERE id = ?", (weak["id"],))
    db.commit()

    monkeypatch.setattr("dojo.cli.DB_PATH", tmp_path / "dojo.db")
    monkeypatch.setattr("dojo.cli.load_conf", lambda *a, **k: {"user": "andy"})
    monkeypatch.setenv("COLUMNS", "220")  # rich squeezes columns to the terminal
    assert _cmd_progress(argparse.Namespace(_user="andy", problems=False)) == 0
    rollup = " ".join(capsys.readouterr().out.split())
    assert "weakest" in rollup
    assert "1.0" in rollup  # the cold problem, not the 45.5 mean
    # The per-problem view is where the strong one is visible.
    assert _cmd_progress(argparse.Namespace(_user="andy", problems=True)) == 0
    detail = " ".join(capsys.readouterr().out.split())
    assert "strong_problem" in detail and "90.0" in detail
    assert "weak_problem" in detail


def test_main_version_flag_reports_the_pyproject_version(cli_env, capsys):
    """`dojo --version` reads the one source of truth (v0.13 follow-up)."""
    import tomllib
    from pathlib import Path

    from dojo.cli import main
    from dojo.version import VERSION

    cli_env  # the fixture still normalizes the environment
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert f"dojo {VERSION}" in capsys.readouterr().out
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    assert VERSION == pyproject["project"]["version"]


def test_main_report_writes_the_student_note_into_the_report(cli_env, monkeypatch):
    """`dojo report <slug> --note TEXT` — the observation reaches the auditor and
    the report JSON on disk."""
    from dojo.cli import main

    rec, db_path, _workbench, _problems = cli_env
    _seed_user(db_path)
    main(["list"])  # seeds the bank

    seen: dict = {}

    def fake_audit(backend, statement, tests, **kwargs):
        seen["note"] = kwargs.get("note")
        return {
            "findings": [],
            "verdict": "ok",
            "explanation": "clean",
            "automated_findings": ["n=3 seed=1: live oracle and fresh oracle disagree"],
            "student_note": kwargs.get("note"),
        }

    monkeypatch.setattr("dojo.curator.audit_curation", fake_audit)
    note = "the generated arrays are not sorted, so O(n) is unachievable"
    assert main(["report", "valid_parentheses", "--note", note]) == 0
    assert seen["note"] == note
    assert "WHAT" not in rec.text  # the note is echoed, not the prompt scaffolding
    assert note in rec.text
    assert "live oracle and fresh oracle disagree" in rec.text  # cross-check shown

    from dojo.config import CURATION_DIR

    # The report lands under DATA_DIR (user state), so the conftest redirect
    # keeps it out of the real repo.
    report_path = CURATION_DIR / "valid_parentheses.report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text())["student_note"] == note


def test_main_report_without_a_note_still_audits(cli_env, monkeypatch):
    from dojo.cli import main

    rec, db_path, _workbench, _problems = cli_env
    _seed_user(db_path)
    main(["list"])

    seen: dict = {}

    def fake_audit(backend, statement, tests, **kwargs):
        seen["note"] = kwargs.get("note")
        return {"findings": [], "verdict": "ok", "explanation": "", "automated_findings": []}

    monkeypatch.setattr("dojo.curator.audit_curation", fake_audit)
    assert main(["report", "valid_parentheses"]) == 0
    assert seen["note"] is None
    assert "No contract violations found." in rec.text
