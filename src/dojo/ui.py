"""Shared rich UI helpers: tables with breathing room between rows."""

from __future__ import annotations

from rich.table import Table


def table(title: str | None = None) -> Table:
    t = Table(title=title)
    t.padding = (1, 1)  # vertical space between rows
    return t
