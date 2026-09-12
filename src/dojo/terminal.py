"""Interactive prompt: prompt_toolkit when attached to a TTY (arrow keys,
editing across wrapped lines, command history), plain console.input
otherwise — which is what tests exercise via FakeConsole.

prompt_toolkit renders no rich markup of its own, so TTY prompts are
converted to ANSI escapes first (`_to_ansi`) — the `[bold cyan]dojo ›`
styling survives instead of being stripped to plain text (v0.8.1).

v0.10.1:
- ``hint`` renders as prompt_toolkit *virtual text* (the bottom toolbar) —
  the command list no longer scrolls as a printed line; on non-TTYs it is
  printed above the prompt so tests and pipes still see it.
- ``patch_console`` wraps a rich Console so prints between prompts route
  through prompt_toolkit.patch_stdout: output written while the fullscreen
  prompt repaints can otherwise be visually truncated (the reported
  "hist" cut-offs — the debug log proved those responses were complete,
  so the loss was in the terminal repaint, not the data).
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


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def make_prompt(console):
    def prompt(text: str, default: str | None = None, hint: str | None = None) -> str:
        global _session
        if not _is_tty():
            if hint:
                console.print(hint)
            return console.input(text)
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import ANSI

            if _session is None:
                _session = PromptSession()
            # ``default`` prefills the answer (editing a previous response);
            # ``hint`` is virtual text in the bottom toolbar — visible, but
            # it never scrolls or takes a line of output.
            kwargs = {}
            if hint is not None:
                kwargs["bottom_toolbar"] = lambda: ANSI(_to_ansi(hint))
            return _session.prompt(ANSI(_to_ansi(text)), default=default, **kwargs)
        except Exception:  # noqa: BLE001 - fall back to the plain prompt
            return console.input(text)

    return prompt


def patch_console(console):
    """Wrap a rich Console for printing *between* interactive prompts:
    prints route through prompt_toolkit's patch_stdout so the fullscreen
    prompt's repaint can't visually truncate them (v0.10.1). No-op for
    non-TTYs — tests and pipes keep the plain path. Any patch_stdout
    failure degrades to a plain print — output is never lost."""
    if not _is_tty():
        return console

    # The context manager lives INSIDE the module prompt_toolkit.patch_stdout
    # (`from prompt_toolkit import patch_stdout` binds the module — calling
    # it was the reported TypeError crash).
    from prompt_toolkit.patch_stdout import patch_stdout as _patch_stdout

    class _Patched:
        def __getattr__(self, name):
            return getattr(console, name)

        def print(self, *args, **kwargs):
            try:
                with _patch_stdout(raw=True):
                    console.print(*args, **kwargs)
            except Exception:  # noqa: BLE001 - degrade, never drop output
                console.print(*args, **kwargs)

    return _Patched()
