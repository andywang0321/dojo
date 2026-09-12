"""AI prose rendering (v0.10.3): the model emits Markdown, rich renders it.

On a TTY the body renders as rich Markdown — headings, lists, emphasis —
with fenced code blocks syntax-highlighted via rich.syntax. On pipes and
in tests rich renders the same structure to plain text, so content
assertions keep working and ``de_markdown`` retires from display duty
(stored transcripts/reviews keep the model's markdown as-is).

The chrome contract: a dim one-line title above the body, no Panel
frames — Markdown headings already structure the text.
"""

from __future__ import annotations

import io

from rich.console import Console
from rich.markdown import Markdown

CODE_THEME = "monokai"


def md_plain(text: str, width: int = 100) -> str:
    """Render markdown to plain text (no ANSI) — deterministic, for table
    cells and the non-TTY/pipe fallback."""
    out = io.StringIO()
    console = Console(file=out, force_terminal=False, no_color=True, width=width)
    console.print(Markdown(text, code_theme=CODE_THEME))
    return out.getvalue().rstrip("\n")


def render_ai(console, title: str, text: str) -> None:
    """Print one AI prose block: a dim title line, then the markdown body."""
    console.print(f"[dim]{title}[/dim]")
    console.print(Markdown(text, code_theme=CODE_THEME))
