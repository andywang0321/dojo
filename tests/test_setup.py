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
        detect_env_key=False,  # pin the prompt path regardless of ambient env
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
        detect_env_key=False,
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
        detect_env_key=False,
    )
    assert summary["user"] == "andy"
    assert load_conf(tmp_path / "dojo.conf") == {"user": "andy"}


# ---------------------------------------------------- key detection (v0.9)

def test_run_wizard_detects_env_key(tmp_path, fake_console, monkeypatch):
    """A DEEPSEEK_API_KEY in the environment is used without prompting and
    persisted to the dotenv so every shell sees it."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    monkeypatch.delenv("DOJO_DEEPSEEK_API_KEY", raising=False)
    console = fake_console([""])  # name prompt → default
    calls = []
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: calls.append(1) or "should-not-run",
    )
    assert calls == []  # no prompt when the key is detected
    assert summary["key_detected"] is True
    assert "DEEPSEEK_API_KEY=sk-from-env" in (tmp_path / ".env").read_text()
    assert "detected" in console.text


def test_run_wizard_detects_existing_dotenv_key(tmp_path, fake_console):
    """A key already in the dotenv skips the prompt, is left untouched, and now
    also names its provider (v0.13: the dotenv records DOJO_PROVIDER)."""
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-existing\n")
    console = fake_console([""])
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: (_ for _ in ()).throw(AssertionError("prompted")),
    )
    assert summary["key_detected"] is True
    content = (tmp_path / ".env").read_text()
    assert "DEEPSEEK_API_KEY=sk-existing" in content
    assert "DOJO_PROVIDER=deepseek" in content


def test_run_wizard_skip_detection_respects_flag(tmp_path, fake_console, monkeypatch):
    """`dojo setup --skip-key` means no key handling at all — env detection
    included, so scripted installs (make seed) never write a key."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    monkeypatch.delenv("DOJO_DEEPSEEK_API_KEY", raising=False)
    console = fake_console([""])
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: "",
        detect_env_key=False,
    )
    assert summary["key_detected"] is False
    assert not (tmp_path / ".env").exists()


def test_the_wizard_can_be_pinned_to_a_provider(tmp_path, fake_console):
    """`dojo setup --provider anthropic` stores the key under Anthropic's
    variable and records the choice, so `dojo` starts on Claude."""
    console = fake_console([""])  # Enter accepts the default name
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: "sk-ant-test",
        detect_env_key=False,
        provider_override="anthropic",
    )
    content = (tmp_path / ".env").read_text()
    assert "ANTHROPIC_API_KEY=sk-ant-test" in content
    assert "DOJO_PROVIDER=anthropic" in content
    assert summary["key_detected"] is False


def test_the_wizard_detects_a_non_default_provider_key(tmp_path, fake_console, monkeypatch):
    """An OPENAI_API_KEY in the environment selects OpenAI — the wizard used to
    look for DeepSeek's variable only, so an OpenAI user was prompted for a key
    they had already exported."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-env")
    for name in ("DEEPSEEK_API_KEY", "DOJO_DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
                 "DOJO_OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    console = fake_console([""])  # the name prompt; the key must not be asked for
    summary = run_wizard(
        console,
        dotenv_path=tmp_path / ".env",
        conf_path=tmp_path / "dojo.conf",
        db_path=tmp_path / "dojo.db",
        problems_dir=tmp_path / "problems",
        default_name="andy",
        key_getter=lambda: (_ for _ in ()).throw(AssertionError("prompted")),
    )
    assert summary["key_detected"] is True
    content = (tmp_path / ".env").read_text()
    assert "OPENAI_API_KEY=sk-openai-env" in content
    assert "DOJO_PROVIDER=openai" in content
    assert "openai" in console.text
