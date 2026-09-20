"""One exception boundary for everything that can fail transiently.

A session must never end in a traceback because an API call blipped, a
subprocess fell over, or the network was away. `cli.main` catches only
`KeyboardInterrupt`, so every AI and subprocess call site needed its own
try/except — two of eleven had one (v0.13 audit, S1.5). Usage:

    with guard(console, "the tutor") as g:
        g.value = ask_tutor(...)
    if not g.ok:
        return          # the session carries on; the student was told why

The failure is printed in one line, the full detail goes to the debug log
(`event: "degraded"`), and `g.error` carries the message for a caller that wants
to react. Exceptions the *student* caused are not the target: this is for the
things outside the session's control, and it deliberately does not swallow
`KeyboardInterrupt`.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from dojo import debuglog


@dataclass
class Guarded:
    ok: bool = True
    error: str | None = None
    value: Any = None
    detail: dict = field(default_factory=dict)


@contextmanager
def guard(console, label: str, guidance: str | None = None):
    """Run a block that may fail without taking the session down.

    ``label`` names the thing in the student's terms ("the tutor", "the scale
    probe", "the reviewer") — the message says what did not happen, never a
    traceback. ``guidance`` is an optional next step ("carrying on without a
    measurement")."""
    box = Guarded()
    try:
        yield box
    except Exception as exc:  # noqa: BLE001 - the whole point of this module
        box.ok = False
        box.error = f"{type(exc).__name__}: {exc}"
        try:
            debuglog.log_event(
                {"event": "degraded", "label": label, "error": box.error}
            )
        except Exception:  # noqa: BLE001 - logging must never be the failure
            pass
        tail = f" — {guidance}" if guidance else " — carrying on."
        console.print(f"[yellow]{label} unavailable ({box.error}){tail}[/yellow]")
