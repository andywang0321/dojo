"""dojo's version — one source of truth, in `pyproject.toml`.

There used to be three answers to one question (audit F13): the tag said
`0.13.0`, `version.MAJOR_VERSION` said `"0.10"`, and `dojo.__version__` said
`0.1.0`. The consequence was not cosmetic — `MAJOR_VERSION` gates debug-log
retention, so the guard its own docstring mandates had not fired for two stages
and `data/logs/dojo.log` grew unbounded.

`VERSION` is the full version from `pyproject.toml` (the checkout is the normal
case; an installed package with no checkout beside it falls back to the wheel's
metadata), and `MAJOR_VERSION` is its major.minor. Shipping a new stage means
editing `pyproject.toml` and nothing else: `MAJOR_VERSION` then differs from the
marker file of the last run, and the next real run clears `data/logs/`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

#: `<repo>/pyproject.toml` — this file lives at `<repo>/src/dojo/version.py`.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _pyproject_version() -> str | None:
    try:
        data = tomllib.loads(_PYPROJECT.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    version = (data.get("project") or {}).get("version")
    return version if isinstance(version, str) and version else None


def _installed_version() -> str | None:
    """The wheel's metadata, for an installed dojo with no checkout beside it."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("dojo")
    except PackageNotFoundError:
        return None


VERSION = _pyproject_version() or _installed_version() or "0.0.0"

#: Major.minor only: the marker the debug log compares against, so a patch
#: release does not throw away history and a new stage does.
MAJOR_VERSION = ".".join(VERSION.split(".")[:2]) or VERSION
