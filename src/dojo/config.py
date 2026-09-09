"""Central configuration: paths and environment resolution.

Nothing here should ever need a network call. The AI backend is chosen by
``DOJO_AI_BACKEND`` (``mock`` or ``deepseek``, default ``deepseek``) so the
whole pipeline is exercisable without an API key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DATA_DIR = REPO_ROOT / "data"
WORKBENCH_DIR = REPO_ROOT / "workbench"
PROBLEM_OVERRIDES = REPO_ROOT / "data" / "problem_overrides.json"
#: The seed corpus: one problem per file, prompt in the module docstring,
#: organized by pattern directory (imported by dojo.bank).
PROBLEMS_DIR = REPO_ROOT / "problems"
DB_PATH = DATA_DIR / "dojo.db"
#: Active-user config (gitignored): {"user": "name"} — one computer, one user.
DOJO_CONF = DATA_DIR / "dojo.conf"


def load_conf(path: Path | None = None) -> dict:
    path = path or DOJO_CONF
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_conf(data: dict, path: Path | None = None) -> None:
    path = path or DOJO_CONF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def ai_backend() -> str:
    return os.environ.get("DOJO_AI_BACKEND", "deepseek")


def deepseek_api_key() -> str | None:
    return (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("DOJO_DEEPSEEK_API_KEY")
        or _read_dotenv("DEEPSEEK_API_KEY")
    )


def _read_dotenv(key: str) -> str | None:
    """Minimal .env reader (no python-dotenv dependency)."""
    dotenv = REPO_ROOT / ".env"
    if not dotenv.exists():
        return None
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip("'\"")
    return None
