"""The workbench artifact and its views (v0.13).

One file, several readers: the student runs it, the judge imports it, the AI
agents read the *student's* code out of it, and `dojo show` keeps the raw truth.
The tests here pin the projection (chrome removed, student's code kept), the
runnable block (built from the problem's own visible tests, never executed by the
grader), and the refusal to write a template that cannot compile.
"""

from __future__ import annotations

import ast

from dojo.db import dumps_json
from dojo.session import workbench as wb


def _problem(
    *,
    slug="p",
    statement="Return true if any duplicate. [Easy]",
    function_name="contains_duplicate",
    signature='(nums: list[int]) -> bool',
    cases=None,
):
    return {
        "slug": slug,
        "statement": statement,
        "function_name": function_name,
        "signature": dumps_json(signature) if not isinstance(signature, str) or signature.startswith(("(", "{")) else signature,
        "visible_tests": dumps_json(cases if cases is not None else [
            {"args": [[1, 2, 3, 3]], "expected": True},
            {"args": [[1, 2]], "expected": False},
        ]),
    }


# ------------------------------------------------------------ the template


def test_template_has_shebang_statement_stub_and_examples():
    source = wb.template_for(_problem())
    ast.parse(source)
    assert source.startswith("#!")
    assert "Return true if any duplicate" in source
    assert "def contains_duplicate(nums: list[int]) -> bool:" in source
    assert "raise NotImplementedError" in source
    assert wb.SENTINEL_OPEN in source and wb.SENTINEL_CLOSE in source
    assert "contains_duplicate(*_args)" in source


def test_a_hostile_statement_still_renders_a_parsing_template():
    for statement in (
        'Return the "sum" — e.g. print("""x""") here',
        'Given x, return "y"',
        r"Match \d+ and \sum the results",
        "print('''x''')",
    ):
        source = wb.template_for(_problem(statement=statement))
        ast.parse(source)
        assert statement.splitlines()[0][:15] in source.replace("\\\\", "\\")


def test_a_template_that_cannot_compile_is_refused():
    import pytest

    broken = _problem(signature={"methods": {"go": "not-a-signature"}})
    with pytest.raises(wb.TemplateError):
        wb.template_for(broken)


def test_the_class_template_replays_ops_cases():
    problem = _problem(
        function_name="MinStack",
        signature={"methods": {"push": "(self, val: int) -> None", "pop": "(self) -> None"}},
        cases=[
            {"ops": [["push", 1], ["pop"]], "expected": [None, None]},
            {"ops": [["push", 2]], "expected": [None]},
        ],
    )
    source = wb.template_for(problem)
    ast.parse(source)
    assert "class MinStack:" in source
    assert "_obj = MinStack(*_ctor)" in source
    assert "getattr(_obj, _m)(*_a)" in source


def test_a_problem_whose_cases_cannot_be_literals_gets_no_block():
    problem = _problem(cases=[{"args": [[1]], "expected": float("inf")}])
    assert wb.example_block(problem) == ""
    source = wb.template_for(problem)
    ast.parse(source)
    assert wb.SENTINEL_OPEN not in source


def test_predicate_cases_are_printed_without_a_local_verdict():
    problem = _problem(cases=[{"args": [[1, 2]], "predicate": "any_valid", "expected": True}])
    block = wb.example_block(problem)
    assert "_want is None" in block
    assert "dojo checks this one by property" in block


def test_an_order_insensitive_problem_compares_that_way_locally():
    problem = _problem(
        function_name="intersection",
        cases=[{"args": [[1, 2]], "expected": [1, 2], "compare": "sorted"}],
    )
    block = wb.example_block(problem)
    assert "_COMPARE = 'sorted'" in block
    assert "sorted(map(repr, _got)) == sorted(map(repr, _want))" in block


# ------------------------------------------------------- the student view


def test_student_view_strips_the_chrome_and_keeps_the_code():
    problem = _problem()
    source = wb.template_for(problem)
    view = wb.student_view(source, problem)
    assert not view.startswith("#!")
    assert "Return true if any duplicate" not in view      # the statement literal
    assert wb.SENTINEL_OPEN not in view and "contains_duplicate(*_args)" not in view
    assert "def contains_duplicate(nums: list[int]) -> bool:" in view
    ast.parse(view)


def test_student_view_keeps_a_docstring_the_student_rewrote():
    problem = _problem()
    source = wb.template_for(problem).replace(
        "Return true if any duplicate. [Easy]",
        "My own note: watch the empty list.",
    )
    view = wb.student_view(source, problem)
    assert "My own note" in view


def test_student_view_keeps_an_examples_block_the_student_edited():
    """Only the block *dojo wrote* is removed. If the student edits inside it,
    it is theirs — the same rule as a rewritten docstring."""
    problem = _problem()
    source = wb.template_for(problem).replace(
        "contains_duplicate(*_args)", "contains_duplicate(*_args)  # mine now"
    )
    view = wb.student_view(source, problem)
    assert "# mine now" in view


def test_student_view_is_idempotent():
    problem = _problem()
    view = wb.student_view(wb.template_for(problem), problem)
    assert wb.student_view(view, problem) == view


def test_is_pristine_tracks_the_template():
    problem = _problem()
    assert wb.is_pristine(wb.template_for(problem), problem)
    assert not wb.is_pristine(wb.template_for(problem) + "\n# typed\n", problem)


def test_a_missing_signature_still_yields_a_callable_stub():
    """`def name:` is not valid Python. A problem curated without a signature
    used to be written out unparseable; now it gets an honest `*args` stub."""
    problem = _problem(signature=None)
    source = wb.template_for(problem)
    ast.parse(source)
    assert "def contains_duplicate(*args, **kwargs):" in source
