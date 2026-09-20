"""The workbench artifact and the *views* of it different readers need (v0.13).

One file is written per session, and it is read by six very different
consumers, each of which wants something different from it:

- **the student** wants the statement, a signature to fill in, and a way to run
  it (the IDE's Run button, F5);
- **the judge and the probe** want the module exactly as it is — they never
  execute the examples block, because both load the file under a name that is not
  ``__main__``;
- **the AI agents** (tutor, reviewer, post-solve discussion) want the *student's*
  code, not dojo's scaffolding. Handing them the raw file produced 15 of 18 live
  reviews complaining about the shebang or the statement-as-docstring, including
  one that cited a ruff finding dojo's own ruff configuration cannot emit;
- **`dojo show`** wants the raw file (the truth of what ran) with a clean view
  available on request.

So the module owns three things: the template, the fenced examples block, and
`student_view()` — the chrome-stripped projection everything AI-facing reads.
The block is delimited by sentinels so stripping is exact rather than heuristic,
and the whole template is validated by `compile()` before it is written: a
statement containing a triple quote, a trailing quote, or a backslash used to
produce a file that did not parse, and the student met it as a "harness error"
on their first `check`.
"""

from __future__ import annotations

import ast
import json

from dojo.config import VENV_PYTHON
from dojo.db import loads_json

SENTINEL_OPEN = "# --- dojo: visible examples (auto-generated — run this file, or press F5) ---"
SENTINEL_CLOSE = "# --- end dojo ---"

STUB_COMMENT = "# Solve it. Use `dojo check` / `dojo hint` from a second terminal."
# NB: the stub is rewritten in v0.13 §C's follow-up wording ("run this file"),
# but the text is user-visible copy pinned by tests — change it deliberately.


class TemplateError(RuntimeError):
    """A problem cannot be rendered into a workbench file that compiles.

    A curation problem, not a student problem — reported as one instead of being
    written out as a file that fails to parse on the first `check` or `submit`."""


def _field(problem, name: str, default=None):
    """Read a column tolerantly: callers hold different projections of a problem
    (a full `problems` row, a joined attempt row, a plain dict in tests), and a
    missing key must degrade rather than raise."""
    try:
        value = problem[name]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def statement_literal(statement: str) -> str:
    """The statement as a string literal that always parses.

    The delimiter is chosen not to appear in the text; a statement ending in a
    quote cannot close a triple-quoted literal, and a backslash inside a plain
    literal is an invalid escape sequence. `repr` is the fallback that cannot be
    broken at all."""
    backslash = chr(92)
    for quote in ('"""', "'''"):
        if quote not in statement and not statement.rstrip().endswith(quote[0]):
            return f"{quote}{statement.replace(backslash, backslash * 2)}{quote}"
    return repr(statement)


def _literal(value) -> str | None:
    """A Python literal for a JSON-ish value, or None if it cannot round-trip."""
    text = repr(value)
    try:
        if ast.literal_eval(text) != value:
            return None
    except (ValueError, SyntaxError):
        return None
    return text


def _args_literal(args: list) -> str | None:
    parts = [_literal(arg) for arg in args]
    if any(part is None for part in parts):
        return None
    return "(" + ", ".join(parts) + ("," if len(parts) == 1 else "") + ")"


def example_block(problem) -> str:
    """The `if __name__ == "__main__":` block built from the problem's own
    visible tests, sentinel-fenced, or "" when it cannot be built honestly.

    Built from `visible_tests` (the same data `check` runs) so the file can never
    disagree with the grader. A case whose comparison needs dojo's checker is
    printed without a local verdict rather than guessed at."""
    cases = loads_json(_field(problem, "visible_tests"), []) or []
    function_name = _field(problem, "function_name")
    if not cases or not function_name:
        return ""

    class_cases = [c for c in cases if "ops" in c]
    plain_cases = [c for c in cases if "ops" not in c]
    if class_cases and plain_cases:
        return ""  # a mixed problem: dojo's own check covers it, don't guess here

    lines = [SENTINEL_OPEN, 'if __name__ == "__main__":']
    if class_cases:
        entries = []
        for case in class_cases:
            ops = _literal(case["ops"])
            want = _literal(case.get("expected"))
            ctor = _literal(case.get("ctor_args", []))
            if ops is None or want is None or ctor is None:
                return ""
            entries.append(f"        ({ops}, {want}, {ctor}),")
        lines += [
            "    _cases = [",
            *entries,
            "    ]",
            "    for _i, (_ops, _want, _ctor) in enumerate(_cases, 1):",
            f"        _obj = {function_name}(*_ctor)",
            "        _got = [getattr(_obj, _m)(*_a) for _m, *_a in _ops]",
            "        _ok = _got == _want",
            "        print(f\"case {_i}: {'ok  ' if _ok else 'FAIL'} got={_got!r} want={_want!r}\")",
        ]
        lines.append(SENTINEL_CLOSE)
        return "\n".join(lines) + "\n"

    entries, modes, has_predicate = [], set(), False
    for case in plain_cases:
        args = _args_literal(list(case.get("args", [])))
        if args is None:
            return ""
        if "predicate" in case:
            has_predicate = True
            entries.append(f"        ({args}, None),")
            continue
        want = _literal(case.get("expected"))
        if want is None:
            return ""
        mode = case.get("compare", "strict")
        modes.add(mode)
        entries.append(f"        ({args}, {want}),")
    if not entries:
        return ""

    lines += ["    _cases = [", *entries, "    ]"]
    if modes - {"strict"}:
        # A comparison helper, but only for the modes this problem actually uses
        # — the common case stays two lines long.
        lines += [
            "",
            "    def _same(_got, _want):",
        ]
        if "sorted" in modes:
            lines += [
                '        if _COMPARE == "sorted":  # dojo accepts any order here',
                "            return sorted(map(repr, _got)) == sorted(map(repr, _want))",
            ]
        approx = sorted(m for m in modes if m.startswith("approx"))
        if approx:
            tol = approx[0].split(":", 1)[1]
            lines += [
                f"        if _COMPARE == {approx[0]!r}:  # float tolerance",
                f"            return abs(_got - _want) <= {tol}",
            ]
        lines += ["        return _got == _want"]
    body_indent = "    " if modes - {"strict"} else "    "
    lines += [
        "    for _i, (_args, _want) in enumerate(_cases, 1):",
        f"        _got = {function_name}(*_args)",
    ]
    if has_predicate:
        lines += [
            "        if _want is None:  # dojo checks this one by property",
            "            print(f\"case {_i}: got={_got!r}\")",
            "            continue",
        ]
    if modes - {"strict"}:
        lines += [
            "        _ok = _same(_got, _want)",
        ]
    else:
        lines += ["        _ok = _got == _want"]
    lines += [
        "        print(f\"case {_i}: {'ok  ' if _ok else 'FAIL'} got={_got!r} want={_want!r}\")",
    ]
    lines.append(SENTINEL_CLOSE)
    block = "\n".join(lines) + "\n"
    if modes - {"strict"}:
        # `_COMPARE` drives the helper; declared once, above the cases.
        compare = sorted(modes - {"strict"})[0]
        block = block.replace(
            "    _cases = [",
            f"    _COMPARE = {compare!r}  # every case here compares this way\n    _cases = [",
            1,
        )
    del body_indent
    return block


def render_template(problem, venv_python=VENV_PYTHON) -> str:
    """The blank workbench file for a problem: shebang, statement, stub, and —
    when it can be built honestly — the runnable examples block."""
    signature = loads_json(_field(problem, "signature"), None)
    statement = _field(problem, "statement", "")
    header = f"#!{venv_python}\n\n{statement_literal(statement)}\n\n\n"
    if isinstance(signature, dict) and "methods" in signature:
        lines = [
            f"class {_field(problem, 'function_name')}:",
            "    def __init__(self):",
            f"        {STUB_COMMENT}",
            "        raise NotImplementedError",
        ]
        for name, sig in signature["methods"].items():
            lines += [
                "",
                f"    def {name}{sig}:",
                f"        {STUB_COMMENT}",
                "        raise NotImplementedError",
            ]
        stub = "\n".join(lines) + "\n"
    elif isinstance(signature, dict) and "functions" in signature:
        stub = "\n\n".join(
            f"def {name}{sig}:\n    {STUB_COMMENT}\n    raise NotImplementedError"
            for name, sig in signature["functions"].items()
        ) + "\n"
    else:
        # No stored signature: `def name:` is not valid Python, and a template
        # that cannot compile must never be written (it used to be, and the
        # student met it as a harness error on their first check). `*args` is
        # honest — the judge calls the function positionally either way.
        signature = signature if isinstance(signature, str) and signature else "(*args, **kwargs)"
        stub = (
            f"def {_field(problem, 'function_name')}{signature}:\n"
            f"    {STUB_COMMENT}\n    raise NotImplementedError\n"
        )
    block = example_block(problem)
    return header + stub + ("\n\n" + block if block else "")


def template_for(problem) -> str:
    """`render_template`, validated: a template that does not compile is a
    curation error, raised here so no caller can write one out."""
    source = render_template(problem)
    try:
        compile(source, f"<template {_field(problem, 'slug', '?')}>", "exec")
    except SyntaxError as exc:
        raise TemplateError(
            f"the template for '{_field(problem, 'slug', '?')}' does not compile "
            f"({exc.msg}, line {exc.lineno}) — `dojo report {problem['slug']}` "
            "audits the curation"
        ) from exc
    return source


def student_view(source: str, problem) -> str:
    """What an AI should read: dojo's chrome removed, the student's code kept.

    Removed: the shebang, the leading statement literal **only when it still
    equals the problem statement** (a student who rewrote it owns it), and the
    sentinel-fenced examples block. Everything else is untouched — this is a
    projection, never a rewrite, so what the model critiques is what ran."""
    statement = (_field(problem, "statement") if problem is not None else None) or None
    lines = source.splitlines()
    drop: set[int] = set()

    if lines and lines[0].startswith("#!") and "python" in lines[0]:
        drop.add(0)

    if statement is not None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None and tree.body:
            first = tree.body[0]
            value = getattr(first, "value", None)
            if (
                isinstance(first, ast.Expr)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value.strip() == statement.strip()
            ):
                end = getattr(first, "end_lineno", None) or first.lineno
                drop.update(range(first.lineno - 1, end))

    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == SENTINEL_OPEN:
            start = i
        elif stripped == SENTINEL_CLOSE and start is not None:
            # Only the block *dojo wrote* is removed: if the student edited
            # inside it, it is theirs now and it stays (the same rule as the
            # statement literal above).
            found = "\n".join(lines[start : i + 1]).strip()
            if found == example_block(problem).strip():
                drop.update(range(start, i + 1))
            break

    kept = [line for i, line in enumerate(lines) if i not in drop]
    text = "\n".join(kept).strip("\n")
    return text + "\n" if text else ""


def is_pristine(source: str, problem) -> bool:
    """True when the file is still exactly the template we wrote (nothing typed
    yet) — used to say so rather than grading a stub as an attempt."""
    try:
        return source.strip() == template_for(problem).strip()
    except TemplateError:
        return False


def example_count(problem) -> int:
    """How many examples the block will run (for the session banner)."""
    block = example_block(problem)
    return block.count("\n        (") if block else 0


__all__ = [
    "SENTINEL_CLOSE",
    "SENTINEL_OPEN",
    "TemplateError",
    "example_block",
    "example_count",
    "is_pristine",
    "render_template",
    "statement_literal",
    "student_view",
    "template_for",
]
