"""Workbench state: what a solve session knows between commands.

The workbench is scratch space (gitignored). Attempt code is persisted to
the DB, not here; this file only carries live session state: the hint tier,
the hint transcript so far, and (once the student submits) the id of the
attempt row that submit created.

The state file is also the only way a session survives a crash: a session
that dies before submitting is resumed by the next invocation, which is why
`quit` retiring the file is a deliberate, total abandonment (v0.11).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from dojo.config import WORKBENCH_DIR


@dataclass
class WorkbenchState:
    slug: str
    user_id: int
    tier: int = 0
    hints: list[dict] = field(default_factory=list)
    started_epoch: float = 0.0
    kind: str = "solve"  # 'solve' | 'warmup' — a session state belongs to one kind
    #: v0.11: the attempt row this session has recorded, if it has submitted
    #: yet. An attempt exists iff the student submitted, so this is None until
    #: the first submit — an abandoned session never has one.
    attempt_id: int | None = None

    @property
    def code_path(self) -> Path:
        return WORKBENCH_DIR / f"{self.slug}.py"


def state_path(slug: str) -> Path:
    return WORKBENCH_DIR / f"{slug}.state.json"


def load_state(slug: str) -> WorkbenchState | None:
    """Load a live session, ignoring keys this version does not know about —
    the workbench outlives an upgrade, so a state file written by an older
    dojo must still be resumable."""
    path = state_path(slug)
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    known = {f.name for f in fields(WorkbenchState)}
    return WorkbenchState(**{k: v for k, v in raw.items() if k in known})


def save_state(state: WorkbenchState) -> None:
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    state_path(state.slug).write_text(json.dumps(asdict(state), indent=2))


def retire_state(slug: str) -> None:
    """End the active session for ``slug``: delete its state file so the next
    ``dojo day <slug>`` starts a fresh session. The workbench code file is
    left in place; it is overwritten by the next session's blank template and
    graded code lives on attempt rows (v0.11: only a submit creates one)."""
    state_path(slug).unlink(missing_ok=True)
