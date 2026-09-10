"""Interactive prompt: prompt_toolkit when attached to a TTY (arrow keys,
editing across wrapped lines, command history), plain console.input
otherwise — which is what tests exercise via FakeConsole."""

from __future__ import annotations

import re
import sys

_session = None


def _plain(text: str) -> str:
    """Strip rich markup tags — prompt_toolkit renders its own formatting."""
    return re.sub(r"\[/?[a-z ]+\]", "", text)


def make_prompt(console):
    def prompt(text: str) -> str:
        global _session
        if not sys.stdin.isatty():
            return console.input(text)
        try:
            from prompt_toolkit import PromptSession

            if _session is None:
                _session = PromptSession()
            return _session.prompt(_plain(text))
        except Exception:  # noqa: BLE001 - fall back to the plain prompt
            return console.input(text)

    return prompt
