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
    """Console stand-in: records prints, serves canned inputs.

    ``actions`` maps a canned answer to a callback fired when that answer is
    popped — the way tests simulate the user editing the workbench file
    during a session (e.g. writing the solution right before "submit")."""

    def __init__(self, answers: list[str] | None = None, actions: dict | None = None):
        self.answers = list(answers or [])
        self.actions = dict(actions or {})
        self.out: list[str] = []

    def print(self, *args, **kwargs):
        self.out.append(" ".join(str(a) for a in args))

    def input(self, prompt: str = "") -> str:
        self.out.append(str(prompt))
        answer = self.answers.pop(0) if self.answers else "quit"
        action = self.actions.get(answer)
        if action:
            action()
        return answer

    @property
    def text(self) -> str:
        return "\n".join(self.out)


@pytest.fixture()
def fake_console():
    def make(answers=None, actions=None):
        return FakeConsole(answers, actions)

    return make
