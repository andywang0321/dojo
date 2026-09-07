"""Problem bank: seed importer + fixture overrides.

The seed importer turns the existing ``problems/**/*.py`` files (prompt in
the module docstring, pattern = parent directory) into ``problems`` rows.
The canonical LeetCode fetcher is a v1 feature; for now the bank is what's
on disk plus ``data/problem_overrides.json`` for curated metadata (function
names, visible tests) that prompts don't carry.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from dojo.config import PROBLEMS_DIR, PROBLEM_OVERRIDES
from dojo.db import dumps_json, now

_HEADER_RE = re.compile(r"^(.*?)\s*[\[\(]\s*(Easy|Medium|Hard)\s*[\]\)]")
_COMPLEXITY_RE = re.compile(
    r"O\s*\(\s*([^)]+?)\s*\)\s+time\s+and\s+O\s*\(\s*([^)]+?)\s*\)\s+space",
    re.IGNORECASE,
)


@dataclass
class ParsedProblem:
    slug: str
    title: str
    difficulty: str
    pattern: str
    statement: str
    expected_time: str | None = None
    expected_space: str | None = None


@dataclass
class ProblemOverride:
    slug: str
    function_name: str
    visible_tests: list[dict] = field(default_factory=list)


def _normalize_complexity(raw: str) -> str:
    inner = re.sub(r"\s+", "", raw.lower())
    mapping = {
        "1": "O(1)",
        "logn": "O(log n)",
        "nlogn": "O(n log n)",
        "n": "O(n)",
        "n^2": "O(n^2)",
        "n2": "O(n^2)",
        "n^3": "O(n^3)",
        "n3": "O(n^3)",
        "2^n": "O(2^n)",
        "n!": "O(n!)",
    }
    return mapping.get(inner, f"O({raw})")


def parse_problem_file(path: Path) -> ParsedProblem | None:
    """Parse a ``problems/**/*.py`` file into a ParsedProblem, or None if it
    doesn't match the expected shape (no docstring / no [Difficulty])."""
    text = path.read_text()
    if not text.startswith(('"""', "'''")):
        return None
    quote = text[:3]
    end = text.find(quote, 3)
    if end == -1:
        return None
    statement = text[3:end].strip()
    header = statement.splitlines()[0].strip()
    match = _HEADER_RE.match(header)
    if not match:
        return None
    title, difficulty = match.group(1).strip(), match.group(2)

    expected_time = expected_space = None
    c = _COMPLEXITY_RE.search(statement)
    if c:
        expected_time = _normalize_complexity(c.group(1))
        expected_space = _normalize_complexity(c.group(2))

    return ParsedProblem(
        slug=path.stem,
        title=title,
        difficulty=difficulty,
        pattern=path.parent.name,
        statement=statement,
        expected_time=expected_time,
        expected_space=expected_space,
    )


def discover_problems(root: Path = PROBLEMS_DIR) -> list[ParsedProblem]:
    problems, skipped = [], []
    for path in sorted(root.rglob("*.py")):
        parsed = parse_problem_file(path)
        if parsed:
            problems.append(parsed)
        else:
            skipped.append(str(path.relative_to(root.parent)))
    if skipped:
        print(f"[seed] skipped {len(skipped)} files without parseable prompts: {', '.join(skipped)}")
    return problems


def load_overrides(path: Path = PROBLEM_OVERRIDES) -> dict[str, ProblemOverride]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {
        slug: ProblemOverride(
            slug=slug,
            function_name=entry["function_name"],
            visible_tests=entry.get("visible_tests", []),
        )
        for slug, entry in raw.items()
    }


def seed_problems(conn: sqlite3.Connection, root: Path = PROBLEMS_DIR) -> int:
    overrides = load_overrides()
    inserted = 0
    for problem in discover_problems(root):
        ov = overrides.get(problem.slug)
        conn.execute(
            """
            INSERT INTO problems
                (slug, title, difficulty, pattern, statement, function_name,
                 expected_time, expected_space, visible_tests, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (slug) DO UPDATE SET
                title = excluded.title,
                difficulty = excluded.difficulty,
                pattern = excluded.pattern,
                statement = excluded.statement,
                function_name = excluded.function_name,
                expected_time = excluded.expected_time,
                expected_space = excluded.expected_space,
                visible_tests = excluded.visible_tests
            """,
            (
                problem.slug,
                problem.title,
                problem.difficulty,
                problem.pattern,
                problem.statement,
                ov.function_name if ov else None,
                problem.expected_time,
                problem.expected_space,
                dumps_json(ov.visible_tests) if ov else None,
                now(),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted
