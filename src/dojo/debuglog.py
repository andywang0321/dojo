"""Debug logging: raw AI traffic for post-hoc debugging.

Everything the AI backend is told and says lands in a gitignored JSONL log
(data/logs/dojo.log by default) — system prompt, user prompt, raw response
before parsing, latency, and transport errors. The log is cleared whenever
the major version bumps (data/logs/.version marker, see dojo/version.py),
so it can never grow unbounded.

Only the live backend logs: MockBackend never writes, so tests stay
offline and deterministic (rule 5). Tests that exercise this module
monkeypatch ``debuglog.LOG_PATH`` onto tmp paths.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from dojo.config import LOGS_DIR
from dojo.version import MAJOR_VERSION

LOG_PATH = LOGS_DIR / "dojo.log"
VERSION_MARKER = LOGS_DIR / ".version"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def maybe_clear_logs(log_dir: Path | None = None, version: str = MAJOR_VERSION) -> bool:
    """Truncate the debug log when the major version changed since the last
    write — the size-explosion guard. Writes the version marker on first
    use. Returns True when a clear (or first init) happened."""
    log_dir = log_dir or LOG_PATH.parent
    marker = log_dir / ".version"
    if marker.exists() and marker.read_text().strip() == version:
        return False
    log_dir.mkdir(parents=True, exist_ok=True)
    for path in log_dir.glob("*.log"):
        path.unlink()
    marker.write_text(version + "\n")
    return True


def log_event(event: dict, log_path: Path | None = None) -> None:
    """Append one event as a JSON line. The marker check runs per write
    (AI calls are sparse), so a version bump clears the log even without a
    restart."""
    log_path = log_path or LOG_PATH
    maybe_clear_logs(log_path.parent)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps({"ts": _now(), **event}, ensure_ascii=False) + "\n")
