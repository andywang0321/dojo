"""Shared fixtures: temp DB, fake console for interactive flows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dojo.db import init_db  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    from dojo.db import connect

    conn = connect(db_path)
    yield conn
    conn.close()


class FakeConsole:
    """Console stand-in: records prints, serves canned inputs."""

    def __init__(self, answers: list[str] | None = None):
        self.answers = list(answers or [])
        self.out: list[str] = []

    def print(self, *args, **kwargs):
        self.out.append(" ".join(str(a) for a in args))

    def input(self, prompt: str = "") -> str:
        return self.answers.pop(0) if self.answers else "quit"

    @property
    def text(self) -> str:
        return "\n".join(self.out)


@pytest.fixture()
def fake_console():
    def make(answers=None):
        return FakeConsole(answers)

    return make
