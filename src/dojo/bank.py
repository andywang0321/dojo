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
from dojo.db import connect, dumps_json, now

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
    signature: str | dict | None = None
    lc_number: int | None = None
    #: v0.12: cap the scale probe's largest input for this problem. Needed when
    #: the algorithm's own cost model only holds below some n (a product that
    #: leaves 32-bit range turns a linear solution superlinear).
    probe_max_n: int | None = None
    #: v0.12: how the scale probe compares the student's output with the
    #: reference's — "strict" (default) or "sorted" for order-insensitive
    #: answers, mirroring the judge's per-case comparators. "none" disables the
    #: comparison for problems whose verdicts are predicates.
    scale_compare: str = "strict"


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
            signature=entry.get("signature"),
            lc_number=entry.get("lc_number"),
            probe_max_n=entry.get("probe_max_n"),
            scale_compare=entry.get("scale_compare", "strict"),
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
                 expected_time, expected_space, visible_tests, signature,
                 lc_number, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (slug) DO UPDATE SET
                title = excluded.title,
                difficulty = excluded.difficulty,
                pattern = excluded.pattern,
                statement = excluded.statement,
                function_name = excluded.function_name,
                expected_time = excluded.expected_time,
                expected_space = excluded.expected_space,
                visible_tests = excluded.visible_tests,
                signature = excluded.signature,
                -- A tagged lc (the TOML's authority, set by the bulk
                -- fetch) must survive reseeds: overrides start at NULL.
                lc_number = COALESCE(excluded.lc_number, problems.lc_number)
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
                dumps_json(ov.signature) if ov and ov.signature else None,
                ov.lc_number if ov else None,
                now(),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def _hand_over_lc_numbers(conn: sqlite3.Connection, doomed: list[str]) -> list[str]:
    """Move a doomed row's LeetCode number to the seed row for the same ladder
    problem, before the row goes.

    A fetcher-landed duplicate is often the only row carrying the number, while
    the corpus row for the roadmap's own title-slug has none (three live cases:
    LC 50, 208, 235). The ladder matches on `problems.lc_number`, so deleting the
    duplicate without handing the number over would silently drop a roadmap
    problem — and `dojo fetch --all` would then re-land the duplicate file it was
    deleted for. Returns the moves it made, as `"<lc> -> <slug>"` strings."""
    if not doomed:
        return []
    from dojo.roadmap import load_roadmap

    by_lc: dict[int, str] = {}
    for group in load_roadmap():
        for entry in group["entries"]:
            number, _, slug = entry.partition("_")
            if number.isdigit():
                by_lc[int(number)] = slug.replace("_", "-")
    received = []
    for slug in doomed:
        row = conn.execute(
            "SELECT lc_number FROM problems WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None or row["lc_number"] is None:
            continue
        lc = row["lc_number"]
        target = by_lc.get(lc)
        if target is None or target == slug:
            continue
        # Never overwrite a tag another row already holds: a conflicting number
        # is a curation problem to see, not to paper over.
        moved = conn.execute(
            "UPDATE problems SET lc_number = ? WHERE slug = ? AND lc_number IS NULL",
            (lc, target),
        ).rowcount
        if moved:
            received.append(f"{lc} -> {target}")
    return received


def prune_stale_problems(
    conn: sqlite3.Connection, root: Path = PROBLEMS_DIR, *, note=None
) -> list[str]:
    """Delete bank rows that no longer correspond to anything on disk.

    The bank is defined as a mirror of ``problems/`` (v0.5), but the reseed is
    additive-only, so a row whose seed file is gone stays forever. Two naming
    conventions for the same problem (the fetcher's LeetCode kebab-case slug
    beside the corpus's snake_case one) left 18 dead duplicates that way, each
    also making the roadmap and `dojo list` show one problem twice.

    The criterion is deliberately the weakest one that cannot lose anything: a
    row with no seed file, no curation, no attempt and no warm-up card. A row
    an attempt references is never touched (`dojo history`/`show` need its
    statement), and a curated or card-bearing row is kept and merely reported —
    deleting something a student earned is not cleanup.

    ``note`` is an optional ``print``-alike, so the CLI startup can say what
    happened instead of silently shrinking the table."""
    files = {path.stem for path in Path(root).rglob("*.py")}
    rows = conn.execute(
        """
        SELECT p.slug,
               (p.function_name IS NOT NULL OR p.visible_tests IS NOT NULL)
                   AS curated,
               EXISTS (SELECT 1 FROM attempts a WHERE a.problem_id = p.id)
                   AS attempted,
               EXISTS (SELECT 1 FROM item_cards c WHERE c.slug = p.slug)
                   AS carded
        FROM problems p
        """
    ).fetchall()
    fileless = [row for row in rows if row["slug"] not in files]
    stale = [
        row["slug"]
        for row in fileless
        if not (row["curated"] or row["attempted"] or row["carded"])
    ]
    stranded = [row["slug"] for row in fileless if row["slug"] not in stale]
    handed_over = _hand_over_lc_numbers(conn, stale)
    if stale:
        conn.executemany("DELETE FROM problems WHERE slug = ?", [(s,) for s in stale])
        conn.commit()
    if note is not None:
        if stale:
            note(
                f"[dim]Pruned {len(stale)} bank row(s) with no problem file: "
                f"{', '.join(sorted(stale))}[/dim]"
            )
        if handed_over:
            note(
                "[dim]Moved ladder number(s) to the problem that owns them: "
                f"{', '.join(handed_over)}[/dim]"
            )
        if stranded:
            note(
                f"[yellow]{len(stranded)} bank row(s) have no problem file — kept "
                "because they carry curation, attempts, or a warm-up card: "
                f"{', '.join(sorted(stranded))}[/yellow]"
            )
    return stale


def ensure_seeded(db_path: Path, root: Path = PROBLEMS_DIR, *, note=None) -> int:
    """The startup reseed (v0.5): the bank always mirrors problems/.
    Idempotent upsert — never deletes rows attempts reference. Runs at the
    CLI entry layer, not in db.connect() (bank imports db; the reverse
    would be circular)."""
    conn = connect(db_path)
    seeded = seed_problems(conn, root)
    prune_stale_problems(conn, root, note=note)
    return seeded
