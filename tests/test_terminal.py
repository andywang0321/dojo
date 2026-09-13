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

    from dojo import debuglog, terminal

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


def test_confirm_typo_requires_confirmation(fake_console):
    from dojo.terminal import confirm_typo

    console = fake_console(["y"])
    assert confirm_typo(console, "qit", ["open", "quit"]) == "quit"
    assert "Did you mean `quit`" in console.text


def test_confirm_typo_declined_is_a_question(fake_console):
    from dojo.terminal import confirm_typo

    console = fake_console(["n"])
    assert confirm_typo(console, "qit", ["open", "quit"]) is None


def test_confirm_typo_ignores_questions_and_exact_commands(fake_console):
    from dojo.terminal import confirm_typo

    console = fake_console([])
    assert confirm_typo(console, "submit?", ["submit", "quit"]) is None  # a question
    assert confirm_typo(console, "check my thing", ["check", "quit"]) is None  # multi-word
    assert confirm_typo(console, "quit", ["quit"]) is None  # exact command
    assert confirm_typo(console, "zzzz", ["quit"]) is None  # no close match


def test_prompt_omits_default_when_none(monkeypatch, capsys):
    """Regression (v0.10.10): prompt_toolkit raises on default=None — the
    kwarg must be omitted entirely. Every session prompt degraded to plain
    input behind this one line (arrow keys, multibyte deletion, missing
    virtual text)."""
    import io

    from rich.console import Console

    from dojo import terminal

    captured = {}

    class RecordingSession:
        def prompt(self, message, **kwargs):
            captured["kwargs"] = kwargs
            return "answer"

    monkeypatch.setattr(terminal, "_is_tty", lambda: True)
    monkeypatch.setattr(terminal, "_session", RecordingSession())
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    prompt = terminal.make_prompt(console)

    assert prompt("Q: ") == "answer"  # no default, no hint
    assert "default" not in captured["kwargs"]
    assert "placeholder" not in captured["kwargs"]

    assert prompt("Q: ", default="previous") == "answer"
    assert captured["kwargs"]["default"] == "previous"
    assert prompt("Q: ", hint="[dim]hint[/dim]") == "answer"
    assert "placeholder" in captured["kwargs"]


def test_hint_is_inline_placeholder(monkeypatch, capsys):
    """The command hint renders as prompt_toolkit *placeholder* text —
    in-line right after the cursor while the input is empty, vanishing on
    the first keystroke (prompt_toolkit's own placeholder behavior). It
    must never be the bottom toolbar (its own line below the input) or
    rprompt (right-aligned)."""
    import io

    from prompt_toolkit.formatted_text import to_formatted_text
    from prompt_toolkit.formatted_text.utils import fragment_list_to_text
    from rich.console import Console

    from dojo import terminal

    captured = {}

    class RecordingSession:
        def prompt(self, message, **kwargs):
            captured["kwargs"] = kwargs
            return "answer"

    monkeypatch.setattr(terminal, "_is_tty", lambda: True)
    monkeypatch.setattr(terminal, "_session", RecordingSession())
    console = Console(file=io.StringIO(), force_terminal=False, width=100)

    terminal.make_prompt(console)("Q: ", hint="[dim]open · check[/dim]")

    assert "placeholder" in captured["kwargs"]
    assert "bottom_toolbar" not in captured["kwargs"]
    assert "rprompt" not in captured["kwargs"]
    plain = fragment_list_to_text(to_formatted_text(captured["kwargs"]["placeholder"]))
    assert "open · check" in plain  # the hint survives the ANSI conversion
