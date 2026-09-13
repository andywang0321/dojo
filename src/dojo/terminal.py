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
            # ``hint`` is virtual text: rendered right-aligned ON the input
            # line itself (rprompt) — the bottom toolbar proved unreliable
            # in some terminals (it never rendered, silently), while the
            # input line is the region every terminal renders for sure.
            # NOTE (v0.10.10): prompt_toolkit's prompt(default=None) raises
            # TypeError — default must be OMITTED, never passed as None. The
            # silent fallback hid this behind every session prompt (arrow
            # keys, multibyte deletion, missing virtual text — all symptoms
            # of this one line; the fallback log caught it).
            kwargs = {}
            if default is not None:
                kwargs["default"] = default
            if hint is not None:
                kwargs["rprompt"] = ANSI(_to_ansi(hint))
            return _session.prompt(ANSI(_to_ansi(text)), **kwargs)
        except Exception as exc:  # noqa: BLE001 - degrade, but never silently
            from dojo import debuglog

            debuglog.log_event(
                {
                    "event": "prompt_fallback",
                    "error": f"{type(exc).__name__}: {exc}",
                    "prompt": text,
                }
            )
            if hint:
                console.print(hint)
            return console.input(text)

    return prompt


def confirm_typo(console, word: str, commands: list[str]) -> str | None:
    """A guard against command typos (v0.10.8): a single non-question word
    that close-matches a session command is confirmed before acting —
    "qit" becomes `quit` only after the user says so; consequences are
    too big (quit parks, learn parks, submit grades) to auto-correct.
    Returns the fixed word, or None to treat the input as a question."""
    import difflib

    word = word.strip().lower()
    if not word or " " in word or word.endswith("?"):
        return None
    if word in commands:
        return None
    matches = difflib.get_close_matches(word, commands, n=1, cutoff=0.8)
    if not matches:
        return None
    fixed = matches[0]
    answer = make_prompt(console)(
        f"[yellow]Did you mean `{fixed}`? [y/N] [/yellow]"
    ).strip().lower()
    return fixed if answer in ("y", "yes") else None


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
