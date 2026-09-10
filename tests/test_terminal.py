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
