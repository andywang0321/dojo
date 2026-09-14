"""The canonical reference: generation, the admission gate, and rollback.

A reference is the performance baseline the probe measures the student against,
so a *wrong* reference is worse than a missing one — it would produce confident
verdicts about the student's code derived from a broken baseline. Everything here
is about that asymmetry: the gate refuses rather than risks, and nothing is
written until the reference has been proved equivalent to the oracle.
"""

import json

import pytest

from dojo.curator.curator import (
    CuratorError,
    add_reference,
    make_isolated_namespace,
    reference_findings,
)
from dojo.db import connect, dumps_json, init_db, now
from dojo.tutor.backend import MockBackend

SLUG = "sum_list"

ORACLE = '''
@oracle("sum_list")
def _sum_list_oracle(values: list[int]) -> int:
    total = 0
    for value in values:
        total += value
    return total
'''

GENERATOR = '''
@judge_case("sum_list")
def _sum_list_case(n: int, rng) -> tuple[list, int]:
    n = max(0, min(n, 12))
    return [[rng.randint(-5, 5) for _ in range(n)]], None
'''

#: Returns the right answer in O(n) — the canonical solution.
GOOD_REFERENCE = '''
@reference("sum_list")
def _sum_list_reference(values: list[int]) -> int:
    return sum(values)
'''

#: Right shape, wrong answer.
WRONG_REFERENCE = '''
@reference("sum_list")
def _sum_list_reference(values: list[int]) -> int:
    return len(values)
'''

#: Blows up on the inputs the generator produces.
RAISING_REFERENCE = '''
@reference("sum_list")
def _sum_list_reference(values: list[int]) -> int:
    return values[0] / 0
'''


def _namespace_with(*, oracle=True, generator=True, reference=None):
    ns = make_isolated_namespace()
    if oracle:
        exec(compile(ORACLE, "<oracle>", "exec"), ns)
    if generator:
        # The generator needs a real expected value; derive it from the oracle.
        source = GENERATOR.replace(
            "return [[rng.randint(-5, 5) for _ in range(n)]], None",
            "case = [rng.randint(-5, 5) for _ in range(n)]\n"
            "    return [case], _sum_list_oracle(case)",
        )
        exec(compile(source, "<generator>", "exec"), ns)
    if reference:
        exec(compile(reference, "<reference>", "exec"), ns)
    return ns


VISIBLE = [
    {"args": [[1, 2, 3]], "expected": 6},
    {"args": [[]], "expected": 0},
]


# --------------------------------------------------------------- the gate


def test_gate_admits_an_agreeing_reference():
    ns = _namespace_with(reference=GOOD_REFERENCE)
    assert reference_findings(SLUG, ns, VISIBLE) == []


def test_gate_rejects_a_disagreeing_reference():
    ns = _namespace_with(reference=WRONG_REFERENCE)
    findings = reference_findings(SLUG, ns, VISIBLE)
    assert findings
    assert "the case expects 6" in findings[0]


def test_gate_rejects_a_raising_reference():
    ns = _namespace_with(reference=RAISING_REFERENCE)
    findings = reference_findings(SLUG, ns, VISIBLE)
    assert findings and "raised" in findings[0]


def test_gate_reports_a_missing_reference():
    ns = _namespace_with()
    assert "no @reference" in reference_findings(SLUG, ns, VISIBLE)[0]


def test_gate_requires_an_oracle_to_anchor_against():
    """Without a brute-force anchor there is nothing to admit the reference
    against, so it must be refused rather than trusted."""
    ns = _namespace_with(oracle=False, reference=GOOD_REFERENCE)
    findings = reference_findings(SLUG, ns, VISIBLE)
    assert findings and "no @oracle" in findings[0]


def test_gate_checks_generated_cases_not_just_visible_ones():
    """A reference that happens to satisfy the two visible examples but not the
    generator is still wrong."""
    sneaky = '''
@reference("sum_list")
def _sum_list_reference(values: list[int]) -> int:
    if values == [1, 2, 3]:
        return 6
    if values == []:
        return 0
    return -99
'''
    ns = _namespace_with(reference=sneaky)
    findings = reference_findings(SLUG, ns, VISIBLE)
    assert findings and "generated" in findings[0]


def test_gate_honours_a_case_compare_mode():
    """Order-insensitive answers are judged the way the judge would judge them."""
    ns = make_isolated_namespace()
    exec(compile(ORACLE, "<oracle>", "exec"), ns)
    exec(
        compile(
            '@judge_case("sum_list")\ndef _c(n, rng):\n    return [[1, 2]], 3',
            "<gen>",
            "exec",
        ),
        ns,
    )
    exec(compile(GOOD_REFERENCE, "<ref>", "exec"), ns)
    # `sum` is order-independent, so this passes either way; the point is that
    # the mode is threaded through rather than ignored.
    assert reference_findings(SLUG, ns, [{"args": [[1, 2]], "expected": 3, "compare": "sorted"}]) == []


def test_gate_uses_the_predicate_checker_when_a_case_has_one():
    ns = _namespace_with(reference=GOOD_REFERENCE)
    exec(
        compile(
            '@checker("is_nonneg")\ndef _is_nonneg(module, got, args):\n    return got >= 0',
            "<checker>",
            "exec",
        ),
        ns,
    )
    ok = [{"args": [[1, 2]], "expected": 0, "predicate": "is_nonneg"}]
    assert reference_findings(SLUG, ns, ok) == []
    ns2 = _namespace_with(reference=WRONG_REFERENCE)
    exec(
        compile(
            '@checker("is_negative")\ndef _is_negative(module, got, args):\n    return got < 0',
            "<checker2>",
            "exec",
        ),
        ns2,
    )
    bad = [{"args": [[1, 2]], "expected": -2, "predicate": "is_negative"}]
    findings = reference_findings(SLUG, ns2, bad)
    assert findings and "is_negative" in findings[0]


# ------------------------------------------------------- install + rollback


@pytest.fixture()
def sandbox(tmp_path):
    """An isolated registry file, namespace, overrides, and a curated problem."""
    overrides_path = tmp_path / "overrides.json"
    registry_path = tmp_path / "registry.py"
    registry_path.write_text("# synthetic registry\n")
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    overrides_path.write_text(
        json.dumps({SLUG: {"function_name": "sum_list", "visible_tests": VISIBLE}}) + "\n"
    )
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO problems
                (slug, title, difficulty, pattern, statement, function_name,
                 expected_time, expected_space, visible_tests, created_at)
            VALUES (?, 'Sum List', 'Easy', 'arrays_and_hashing', 'Sum it.',
                    'sum_list', 'O(n)', 'O(1)', ?, ?)
            """,
            (SLUG, dumps_json(VISIBLE), now()),
        )
        conn.commit()
    namespace = _namespace_with()
    return overrides_path, registry_path, db_path, namespace


def test_add_reference_installs_a_gated_reference(sandbox):
    overrides_path, registry_path, db_path, namespace = sandbox
    summary = add_reference(
        SLUG,
        MockBackend(referencer={"reference_code": GOOD_REFERENCE, "note": "sum()"}),
        overrides_path=overrides_path,
        registry_path=registry_path,
        registry_namespace=namespace,
        db_path=db_path,
        verify=lambda: (True, "verified"),
    )
    assert summary["slug"] == SLUG
    assert summary["note"] == "sum()"
    assert '@reference("sum_list")' in registry_path.read_text()
    assert SLUG in namespace["REFERENCES"]


def test_add_reference_writes_nothing_when_the_reference_disagrees(sandbox):
    """The failure path that matters: a wrong reference must never reach the
    registry, because the probe would then measure every future attempt of this
    problem against it."""
    overrides_path, registry_path, db_path, namespace = sandbox
    before = registry_path.read_text()
    with pytest.raises(CuratorError, match="disagrees with the oracle"):
        add_reference(
            SLUG,
            MockBackend(referencer={"reference_code": WRONG_REFERENCE}),
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (True, "verified"),
        )
    assert registry_path.read_text() == before
    assert SLUG not in namespace["REFERENCES"]


def test_add_reference_rolls_back_when_the_verification_gate_fails(sandbox):
    overrides_path, registry_path, db_path, namespace = sandbox
    before = registry_path.read_text()
    with pytest.raises(CuratorError, match="verification gate failed"):
        add_reference(
            SLUG,
            MockBackend(referencer={"reference_code": GOOD_REFERENCE}),
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (False, "tests failed"),
        )
    assert registry_path.read_text() == before
    assert SLUG not in namespace["REFERENCES"]


def test_add_reference_requires_an_oracle(sandbox):
    overrides_path, registry_path, db_path, namespace = sandbox
    namespace["ORACLES"].clear()
    with pytest.raises(CuratorError, match="no @oracle"):
        add_reference(
            SLUG,
            MockBackend(referencer={"reference_code": GOOD_REFERENCE}),
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (True, "verified"),
        )


def test_add_reference_refuses_to_replace_without_force(sandbox):
    overrides_path, registry_path, db_path, namespace = sandbox
    exec(compile(GOOD_REFERENCE, "<ref>", "exec"), namespace)
    with pytest.raises(CuratorError, match="already has a reference"):
        add_reference(
            SLUG,
            MockBackend(referencer={"reference_code": GOOD_REFERENCE}),
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (True, "verified"),
        )


def test_add_reference_rejects_unknown_and_uncurated_slugs(sandbox):
    overrides_path, registry_path, db_path, namespace = sandbox
    backend = MockBackend(referencer={"reference_code": GOOD_REFERENCE})
    with pytest.raises(CuratorError, match="unknown problem"):
        add_reference(
            "nope", backend, overrides_path=overrides_path,
            registry_path=registry_path, registry_namespace=namespace, db_path=db_path,
        )
    with connect(db_path) as conn:
        conn.execute("UPDATE problems SET function_name = NULL WHERE slug = ?", (SLUG,))
        conn.commit()
    with pytest.raises(CuratorError, match="not curated"):
        add_reference(
            SLUG, backend, overrides_path=overrides_path,
            registry_path=registry_path, registry_namespace=namespace, db_path=db_path,
        )
