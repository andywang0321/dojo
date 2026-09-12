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

    from dojo import terminal

    monkeypatch.setattr(terminal, "_is_tty", lambda: True)
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    patched = terminal.patch_console(console)
    patched.print("hello patch")
    where = console.file.getvalue() + capsys.readouterr().out
    assert "hello patch" in where


def test_prompt_fallback_logs_and_prints_hint(monkeypatch, tmp_path):
    """The TTY path's failure mode must never be silent again: a broken
    prompt_toolkit session logs a prompt_fallback event to the debug log,
    prints the hint, and degrades to plain input."""
    import json

    from dojo import terminal
    from dojo import debuglog

    class BrokenSession:
        def prompt(self, *args, **kwargs):
            raise RuntimeError("terminal exploded")

    class FakeConsole:
        def __init__(self):
            self.out = []

        def print(self, *args):
            self.out.append(" ".join(str(a) for a in args))

        def input(self, text):
            self.out.append(str(text))
            return "answer"

    monkeypatch.setattr(terminal, "_is_tty", lambda: True)
    monkeypatch.setattr(terminal, "_session", BrokenSession())
    monkeypatch.setattr(debuglog, "LOG_PATH", tmp_path / "logs" / "dojo.log")

    fake = FakeConsole()
    assert terminal.make_prompt(fake)("Q: ", hint="[dim]the hint[/dim]") == "answer"
    assert "the hint" in " ".join(fake.out)  # hint printed, not lost

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "dojo.log").read_text().splitlines()
    ]
    assert events[0]["event"] == "prompt_fallback"
    assert "terminal exploded" in events[0]["error"]
