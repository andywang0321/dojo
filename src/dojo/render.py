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

REVIEW_DIMS = (
    "correctness",
    "approach_quality",
    "style_idiom",
    "naming",
    "edge_cases",
    "complexity_claim_check",
    "complexity_reasoning",
)


def review_markdown(review: dict) -> str:
    """The rubric as prose markdown (v0.10.11): one "## Dimension — score"
    heading per rubric entry with the comment rendered as-is (markdown
    preserved — the old table flattened comments into one narrow column
    and produced wall-of-newline artifacts). Prose fields follow."""
    lines = []
    for dim in REVIEW_DIMS:
        entry = review.get(dim, {})
        if not isinstance(entry, dict):
            continue
        score = entry.get("score", "?")
        comment = str(entry.get("comment", "")).strip()
        lines.append(f"## {dim.replace('_', ' ').title()} — {score}/5")
        if comment:
            lines.append(comment)
    if review.get("reflection_feedback"):
        lines.append(f"## On your reflection\n\n{review['reflection_feedback']}")
    if review.get("broader_picture"):
        lines.append(f"## Broader picture\n\n{review['broader_picture']}")
    if review.get("overall_comment"):
        lines.append(f"## Overall\n\n{review['overall_comment']}")
    return "\n\n".join(lines)


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
