"""Interactive prompt: prompt_toolkit when attached to a TTY (arrow keys,
editing across wrapped lines, command history), plain console.input
otherwise — which is what tests exercise via FakeConsole.

prompt_toolkit renders no rich markup of its own, so TTY prompts are
converted to ANSI escapes first (`_to_ansi`) — the `[bold cyan]dojo ›`
styling survives instead of being stripped to plain text (v0.8.1).
"""

from __future__ import annotations

import sys

_session = None


def _to_ansi(text: str) -> str:
    """Rich markup → ANSI escapes for prompt_toolkit. A temporary rich
    Console (terminal forced) captures the styled render; plain text passes
    through without escape codes."""
    from rich.console import Console as RichConsole

    capture_console = RichConsole(color_system="standard", force_terminal=True, width=1000)
    with capture_console.capture() as capture:
        capture_console.print(text, end="")
    return capture.get()


def make_prompt(console):
    def prompt(text: str, default: str | None = None) -> str:
        global _session
        if not sys.stdin.isatty():
            return console.input(text)
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import ANSI

            if _session is None:
                _session = PromptSession()
            # ``default`` prefills the answer (editing a previous response);
            # the non-TTY path ignores it — tests and piped sessions re-ask
            # plainly, and the confirm screen shows the previous value.
            return _session.prompt(ANSI(_to_ansi(text)), default=default)
        except Exception:  # noqa: BLE001 - fall back to the plain prompt
            return console.input(text)

    return prompt
