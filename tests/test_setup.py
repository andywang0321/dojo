"""The setup wizard: pure logic against tmp paths — never touches real state."""

import os

from dojo.config import load_conf
from dojo.setup import (
    append_rc,
    default_user_name,
    install_wrapper,
    rc_line,
    run_wizard,
    wrapper_script,
    write_key,
)


def test_write_key_appends_to_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text("EXISTING=1\n")
    write_key(env, "sk-secret")
    content = env.read_text()
    assert "EXISTING=1" in content
    assert "DEEPSEEK_API_KEY=sk-secret" in content


def test_write_key_creates_dotenv(tmp_path):
    env = tmp_path / ".env"
    write_key(env, "sk-secret")
    assert env.read_text().strip() == "DEEPSEEK_API_KEY=sk-secret"


def test_default_user_name_prefers_env_then_git():
    assert default_user_name("andy", None) == "andy"
    assert default_user_name(None, "Andy Wang") == "andy"
    assert default_user_name(None, None) == ""


def test_wrapper_script_and_install(tmp_path):
    bin_dir = tmp_path / "bin"
    script = wrapper_script("/repo/dojo")
    assert script.startswith("#!/bin/sh")
    assert "uv run --project '/repo/dojo' dojo" in script
    path = install_wrapper(bin_dir, "/repo/dojo")
    assert path == bin_dir / "dojo"
    assert os.access(path, os.X_OK)


def test_rc_line_and_append(tmp_path):
    rc = tmp_path / ".zshrc"
    line = rc_line(str(tmp_path / "bin"))
    append_rc(rc, line)
    append_rc(rc, line)  # appending twice must not duplicate
    assert rc.read_text().count(line) == 1


def test_run_wizard_happy_path(tmp_path, fake_console):
    console = fake_console([""])  # user prompt → default
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: "sk-live",
        path_install=lambda: True,
    )
    assert summary["user"] == "andy"
    assert "DEEPSEEK_API_KEY=sk-live" in (tmp_path / ".env").read_text()
    assert load_conf(tmp_path / "dojo.conf") == {"user": "andy"}
    assert summary["path_installed"] is True
    assert summary["seeded"] >= 0


def test_run_wizard_skips_key_when_blank(tmp_path, fake_console):
    console = fake_console(["bea"])
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: "",
        path_install=lambda: False,
    )
    assert summary["user"] == "bea"
    assert not (tmp_path / ".env").exists()
    assert summary["path_installed"] is False


def test_run_wizard_user_override_skips_prompt(tmp_path, fake_console):
    console = fake_console([])  # no answers: the override must avoid prompting
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        user_override="andy",
        key_getter=lambda: "",
    )
    assert summary["user"] == "andy"
    assert load_conf(tmp_path / "dojo.conf") == {"user": "andy"}
