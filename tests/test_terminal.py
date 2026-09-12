"""Terminal prompt: rich markup → ANSI for prompt_toolkit (v0.8.1).

prompt_toolkit renders no rich markup of its own; the pre-v0.8.1 code
stripped all tags, which flattened the bold-cyan `dojo ›` prompt to plain
text on TTYs. `_to_ansi` converts rich markup to ANSI escapes instead, so
the prompt keeps its styling while the non-TTY path (tests) still passes
markup through to `console.input` untouched.
"""

from dojo.terminal import _to_ansi


def test_to_ansi_keeps_text_and_emits_styles():
    out = _to_ansi("[bold cyan]dojo ›[/bold cyan]")
    assert "dojo ›" in out
    assert "\x1b[" in out  # ANSI escape sequences present
    assert "[bold" not in out  # markup consumed, never leaked to the prompt


def test_to_ansi_plain_text_stays_plain():
    out = _to_ansi("hello")
    assert "hello" in out
    assert "\x1b[" not in out


def test_make_prompt_accepts_default_non_tty(fake_console):
    """The prefill parameter (editing a previous answer) is TTY-only
    sugar; the non-TTY path must accept it without error."""
    from dojo.terminal import make_prompt

    console = fake_console(["answer"])
    assert make_prompt(console)("Q: ", default="previous") == "answer"


def test_patch_console_never_loses_output(monkeypatch, capsys):
    """Regression: the patch_stdout import must bind the context manager,
    not the module (the reported TypeError crash) — and any patch failure
    degrades to a plain print, never lost output."""
    import io

    from rich.console import Console

    import dojo.terminal as terminal

    monkeypatch.setattr(terminal, "_is_tty", lambda: True)
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    patched = terminal.patch_console(console)
    patched.print("hello patch")
    where = console.file.getvalue() + capsys.readouterr().out
    assert "hello patch" in where
