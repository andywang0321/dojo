"""Learning mode (v0.8): a topic teacher with a practice handoff.

``run_learn`` runs a conversation with the teacher agent — a primer, then a
free exchange where every bare line is a message — persisting the transcript
after each exchange (a crash loses at most one turn). ``practice`` ends the
session with a handoff to an unsolved problem; the caller then starts a
normal blank-template solve session.

The never-solve boundary is deliberately narrowed here: the teacher's context
is the topic name and the conversation only — never a problem statement — so
topic-canonical code is legitimate teaching (see docs/architecture.md).
"""

from __future__ import annotations

import difflib
import re
import sqlite3

from rich.console import Console
from rich.panel import Panel

from dojo import scheduler
from dojo.db import (
    get_or_create_user,
    record_learn_session,
    update_learn_transcript,
)
from dojo.patterns import PATTERNS
from dojo.render import render_ai
from dojo.terminal import make_prompt, patch_console
from dojo.tutor.prompts import TEACHER_SYSTEM, build_teacher_prompt

LEARN_COMMANDS_HINT = "practice (hand off to a problem) · done — or ask"

EXIT_WORDS = ("done", "quit", "q")


def resolve_pattern(topic: str) -> tuple[str | None, str | None]:
    """Topic → pattern. Exact match is case-, space-, and underscore-
    insensitive ('binary search' → 'binary_search'); otherwise a difflib
    did-you-mean suggestion, or (None, None) for no close match."""
    normalized = re.sub(r"\s+", "_", topic.strip().lower())
    for pattern in PATTERNS:
        if pattern == normalized:
            return pattern, None
    matches = difflib.get_close_matches(normalized, list(PATTERNS), n=1, cutoff=0.6)
    return None, matches[0] if matches else None


def run_learn(
    conn: sqlite3.Connection,
    console: Console,
    backend,
    user_name: str,
    pattern: str,
    handoff_slug: str | None = None,
) -> dict:
    """The learning-mode conversation. Returns {"practice": slug} when the
    student accepts a handoff (the caller starts a fresh solve session on
    that slug), else {"practice": None} on graceful exit."""
    user_id = get_or_create_user(conn, user_name)
    console = patch_console(console)  # prints can't be truncated by prompt repaints
    transcript: list[dict] = []
    session_id = record_learn_session(conn, user_id, pattern, transcript)
    prompt = make_prompt(console)

    console.print(
        Panel(
            f"[bold]Learning mode — {pattern}[/bold]\n\n"
            "Type questions freely; the teacher may show topic-canonical code. "
            "`practice` hands off to a problem, `done` ends the session.",
            title="dojo learn",
        )
    )

    def teacher_says(message: str | None = None) -> str:
        if message is not None:
            transcript.append({"role": "student", "text": message})
        answer = backend.chat(TEACHER_SYSTEM, build_teacher_prompt(pattern, transcript))
        transcript.append({"role": "teacher", "text": answer})  # raw markdown
        update_learn_transcript(conn, session_id, transcript)
        return answer

    primer = teacher_says()
    render_ai(console, f"teacher — {pattern}", primer)

    while True:
        raw = prompt(
            "[bold cyan]learn ›[/bold cyan] ",
            hint=f"[dim]{LEARN_COMMANDS_HINT}[/dim]",
        ).strip()
        if not raw:
            continue
        if raw in EXIT_WORDS:
            update_learn_transcript(conn, session_id, transcript, completed=True)
            return {"practice": None}
        if raw == "practice":
            slug = handoff_slug or _pick_practice_slug(conn, user_id, pattern)
            if slug is None:
                console.print(
                    "[yellow]No unsolved curated problem in this pattern to "
                    "practice yet — keep exploring, or `done`.[/yellow]"
                )
                continue
            question = (
                f"Ready to retry '{slug}' with a fresh template? [y/N] "
                if handoff_slug
                else f"Ready to practice on '{slug}'? [y/N] "
            )
            if prompt(question).strip().lower() in ("y", "yes"):
                update_learn_transcript(conn, session_id, transcript, completed=True)
                return {"practice": slug}
            console.print("[dim]Staying in learn mode.[/dim]")
            continue
        render_ai(console, f"teacher — {pattern}", teacher_says(raw))


def _pick_practice_slug(
    conn: sqlite3.Connection, user_id: int, pattern: str
) -> str | None:
    problem = scheduler.pick_practice_problem(conn, user_id, pattern)
    return problem["slug"] if problem else None
