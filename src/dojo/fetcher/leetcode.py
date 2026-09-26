"""LeetCode GraphQL intake (v0.3): fetch a problem and render it into the
dojo seed format, plus the starter-code signature as a curator hint.

Offline-safe by construction: the transport is a plain callable injected at
call sites, so tests pin our contract against fixtures instead of the live
endpoint. (The GraphQL schema is unversioned — parse defensively.)
"""

from __future__ import annotations

import ast
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dojo.bank import seed_problems
from dojo.db import connect
from dojo.fetcher.htmltext import HTMLToText
from dojo.guard import is_network_error, network_message
from dojo.patterns import pattern_for_tags

GRAPHQL_URL = "https://leetcode.com/graphql/"
PROBLEM_URL = "https://leetcode.com/problems/{slug}/"

QUERY = """query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    titleSlug
    difficulty
    content
    topicTags { name slug }
    codeSnippets { lang langSlug code }
  }
}"""


class LeetCodeError(RuntimeError):
    """Fetch/parse failure, with a human-readable cause."""


@dataclass
class ParsedProblem:
    title_slug: str
    title: str
    difficulty: str
    pattern: str
    statement: str  # seed format: "Title [Difficulty]" on the first line
    function_name: str | None
    signature: str | dict | None
    url: str


def fetch_question_data(post, title_slug: str) -> dict:
    """POST the GraphQL query; raises LeetCodeError on any failure."""

    payload = {"query": QUERY, "variables": {"titleSlug": title_slug}}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "dojo/0.3 personal-study fetcher",
    }
    try:
        status, text = post(GRAPHQL_URL, payload, headers)
    except Exception as exc:  # noqa: BLE001 - any transport failure is one
        if is_network_error(exc):
            # Same plain-language line as an unreachable AI backend, one noun
            # different: the student's connection is the thing to check either way.
            raise LeetCodeError(network_message("LeetCode")) from exc
        raise LeetCodeError(f"transport error: {exc}") from exc
    if status != 200:
        raise LeetCodeError(f"HTTP {status}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LeetCodeError(f"response is not JSON: {exc}") from exc


def _normalize_annotation(text: str) -> str:
    # Optional[X] → "X | None" — the balanced match stops at X's own
    # closing bracket instead of the first ']' in the string.
    for _ in range(2):  # twice for Optional[Optional[...]]
        text = re.sub(
            r"Optional\[((?:[^\[\]]|\[[^\[\]]*\])*)\]", r"\1 | None", text
        )
    for src, dst in (
        ("List[", "list["),
        ("Dict[", "dict["),
        ("Set[", "set["),
        ("Tuple[", "tuple["),
        ("Any", "any"),
    ):
        text = text.replace(src, dst)
    return text


def _ensure_bodies(source: str) -> str:
    """LeetCode starter snippets end function/class bodies with blank lines,
    which ast.parse rejects. Pad empty bodies with `pass`."""
    lines = source.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        stripped = line.strip()
        if stripped.endswith(":") and (
            stripped.startswith("def ") or stripped.startswith("class ")
        ):
            indent = len(line) - len(line.lstrip())
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            next_indent = len(nxt) - len(nxt.lstrip()) if nxt.strip() else -1
            if next_indent <= indent:
                out.append(" " * (indent + 4) + "pass")
    return "\n".join(out)


def parse_python_signature(snippet: str) -> dict:
    """Extract function_name + signature from a LeetCode python3 starter
    snippet. One def (optionally wrapped in `class Solution`) → a function;
    several defs or an __init__ → a class ("methods" dict; __init__ dropped —
    the template writes its own). Annotations are normalized to builtin
    generics (List[int] → list[int], Optional[X] → X | None) so the stub
    renders without a typing import."""
    tree = ast.parse(_ensure_bodies(snippet))
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    def render(fn: ast.FunctionDef, is_method: bool) -> str:
        args = [a for a in fn.args.args if a.arg != "self"]
        parts = []
        for arg in args:
            ann = _normalize_annotation(ast.unparse(arg.annotation)) if arg.annotation else None
            parts.append(f"{arg.arg}: {ann}" if ann else arg.arg)
        ret = _normalize_annotation(ast.unparse(fn.returns)) if fn.returns else None
        prefix = "self" + (", " if parts else "") if is_method else ""
        sig = f"({prefix}{', '.join(parts)})"
        return sig + (f" -> {ret}" if ret else "")

    names = [fn.name for fn in defs]
    if classes and (len(defs) > 1 or "__init__" in names):
        methods = {
            fn.name: render(fn, is_method=True)
            for fn in defs
            if fn.name != "__init__"
        }
        return {
            "function_name": classes[0].name,
            "signature": {"methods": methods},
        }
    only = next((fn for fn in defs if fn.name != "__init__"), None)
    if only is None:
        name = classes[0].name if classes else "Solution"
        return {"function_name": name, "signature": None}
    return {"function_name": only.name, "signature": render(only, is_method=False)}


def parse_question(raw: dict) -> ParsedProblem:
    """Validate + convert a GraphQL response into seed-format artifacts."""
    question = (raw.get("data") or {}).get("question")
    if not question:
        raise LeetCodeError("unknown problem (no question in the response)")
    title = question.get("title") or ""
    title_slug = question.get("titleSlug") or ""
    difficulty = question.get("difficulty") or ""
    if difficulty not in ("Easy", "Medium", "Hard"):
        raise LeetCodeError(f"unexpected difficulty {difficulty!r}")
    tags = [t.get("slug") for t in question.get("topicTags") or [] if t.get("slug")]
    pattern = pattern_for_tags(tags)
    body = HTMLToText().convert(question.get("content") or "")
    statement = f"{title} [{difficulty}]\n\n{body}".strip()

    snippet = next(
        (
            s.get("code") or ""
            for s in question.get("codeSnippets") or []
            if s.get("langSlug") == "python3" or s.get("lang") == "Python3"
        ),
        "",
    )
    parsed_sig = parse_python_signature(snippet) if snippet.strip() else None
    return ParsedProblem(
        title_slug=title_slug,
        title=title,
        difficulty=difficulty,
        pattern=pattern,
        statement=statement,
        function_name=parsed_sig["function_name"] if parsed_sig else None,
        signature=parsed_sig["signature"] if parsed_sig else None,
        url=PROBLEM_URL.format(slug=title_slug),
    )


def land(
    problem: ParsedProblem,
    *,
    problems_dir: Path,
    db_path: Path,
) -> Path:
    """Write the seed-format problem file and re-seed the bank. The problem
    lands uncurated (— in `dojo list`); curation upgrades it."""
    path = problems_dir / problem.pattern / f"{problem.title_slug}.py"
    if path.exists():
        raise LeetCodeError(f"'{problem.title_slug}' is already in the bank: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'"""{problem.statement}"""\n')
    seed_problems(connect(db_path), problems_dir)
    return path


def urllib_post(url: str, payload: dict, headers: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read().decode("utf-8", "replace")


def fetch_problem(title_slug: str, *, post=urllib_post) -> ParsedProblem:
    return parse_question(fetch_question_data(post, title_slug))
