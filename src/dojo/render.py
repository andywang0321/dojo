"""AI prose rendering (v0.10.3): the model emits Markdown, rich renders it.

On a TTY the body renders as rich Markdown — headings, lists, emphasis —
with fenced code blocks syntax-highlighted via rich.syntax. On pipes and
in tests rich renders the same structure to plain text, so content
assertions keep working and ``de_markdown`` retires from display duty
(stored transcripts/reviews keep the model's markdown as-is).

The chrome contract (v0.10.4): the markdown body sits inside a bordered
Panel with the context as its title — the frame separates AI prose from
dojo's own chrome, while the headings structure the prose inside it.
"""

from __future__ import annotations

import io

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

CODE_THEME = "monokai"


def md_plain(text: str, width: int = 100) -> str:
    """Render markdown to plain text (no ANSI) — deterministic, for table
    cells and the non-TTY/pipe fallback."""
    out = io.StringIO()
    console = Console(file=out, force_terminal=False, no_color=True, width=width)
    console.print(Markdown(text, code_theme=CODE_THEME))
    return out.getvalue().rstrip("\n")


def render_ai(console, title: str, text: str, border_style: str = "blue") -> None:
    """Print one AI prose block: a bordered Panel whose content is the
    markdown body."""
    console.print(
        Panel(Markdown(text, code_theme=CODE_THEME), title=title, border_style=border_style)
    )
