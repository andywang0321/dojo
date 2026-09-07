"""Workbench state: what a solve session knows between commands.

The workbench is scratch space (gitignored). Attempt code is persisted to
the DB, not here; this file only carries live session state: which attempt,
what hint tier, and the hint transcript so far.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dojo.config import WORKBENCH_DIR


@dataclass
class WorkbenchState:
    slug: str
    attempt_id: int
    user_id: int
    tier: int = 0
    hints: list[dict] = field(default_factory=list)
    started_epoch: float = 0.0
    kind: str = "solve"  # 'solve' | 'warmup' — a session state belongs to one kind

    @property
    def code_path(self) -> Path:
        return WORKBENCH_DIR / f"{self.slug}.py"


def state_path(slug: str) -> Path:
    return WORKBENCH_DIR / f"{slug}.state.json"


def load_state(slug: str) -> WorkbenchState | None:
    path = state_path(slug)
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return WorkbenchState(**raw)


def save_state(state: WorkbenchState) -> None:
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    state_path(state.slug).write_text(json.dumps(asdict(state), indent=2))


def retire_state(slug: str) -> None:
    """End the active session for ``slug``: delete its state file so the next
    ``dojo day <slug>`` starts a fresh attempt (one invocation = one attempt
    row). The workbench code file is left in place; attempt code lives in the
    DB."""
    state_path(slug).unlink(missing_ok=True)
