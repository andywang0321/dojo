"""Roadmap data (v0.10): the NeetCode-150 progression.

Parses the vendored data/roadmap.toml (18 ordered technique groups, each
an ordered problem ladder of LeetCode numbers) into the structures the
scheduler and the `dojo roadmap` view consume. Unknown group names fail
loudly — the taxonomy and the roadmap must never drift silently apart.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from dojo.config import DATA_DIR
from dojo.patterns import GROUP_SLUGS

ROADMAP_PATH = DATA_DIR / "roadmap.toml"


class RoadmapError(RuntimeError):
    """The roadmap data is malformed — never a silent wrong order."""


def load_roadmap(path: Path | None = None) -> list[dict]:
    """The roadmap groups in order:
    ``[{"slug": dojo-pattern, "name": display name, "problems": [lc, ...]}]``."""
    path = path or ROADMAP_PATH
    raw = tomllib.loads(path.read_text())["groups"]
    groups: list[dict] = []
    seen: set[str] = set()
    for group in sorted(raw, key=lambda g: g["order"]):
        name = group["name"]
        slug = GROUP_SLUGS.get(name)
        if slug is None:
            raise RoadmapError(f"roadmap group '{name}' has no dojo pattern mapping")
        if slug in seen:
            raise RoadmapError(f"duplicate roadmap group '{name}'")
        seen.add(slug)
        problems = []
        for entry in group["problems"]:
            try:
                problems.append(int(entry.split("_", 1)[0]))
            except ValueError as exc:
                raise RoadmapError(
                    f"roadmap problem '{entry}' has no LeetCode number prefix"
                ) from exc
        groups.append({"slug": slug, "name": name, "order": group["order"], "problems": problems})
    return groups


def group_index(groups: list[dict], pattern: str) -> int:
    """The roadmap position of a pattern; -1 when it is not in the roadmap."""
    for i, group in enumerate(groups):
        if group["slug"] == pattern:
            return i
    return -1


def next_ladder_problem(
    groups: list[dict], pattern: str, solved_lc: set[int], bank_lc: set[int]
) -> int | None:
    """The earliest unsolved ladder problem of ``pattern`` that actually
    exists in the bank — the roadmap's "next up" within a group. Ladder
    problems not yet fetched are skipped, not blockers."""
    index = group_index(groups, pattern)
    if index < 0:
        return None
    for lc in groups[index]["problems"]:
        if lc not in bank_lc:
            continue
        if lc in solved_lc:
            continue
        return lc
    return None
