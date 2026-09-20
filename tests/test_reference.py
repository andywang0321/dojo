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


# ------------------------------------------- model shape variance (the real bug)

#: What the model actually returned in the first live run: a correct canonical
#: solution with no decorator at all. Every one of the 48 logged proposals looked
#: like this, so `dojo reference --all` refused the entire bank while reporting a
#: gate failure that had never compared anything.
UNDECORATED = '''
def sum_list(values: list[int]) -> int:
    return sum(values)
'''

WRONG_SLUG = '''
@reference("sum-list")
def _sum_list_reference(values: list[int]) -> int:
    return sum(values)
'''


def test_the_prompt_gives_the_model_the_slug_and_the_decorator():
    """The prompt contract. Without the slug the model cannot write the
    decorator, and without the instruction it does not know one is required —
    which is exactly how the first live run failed 48 times."""
    from dojo.curator.prompts import REFERENCE_SYSTEM, build_reference_prompt

    prompt = build_reference_prompt(
        "sum_list", "Sum List [Easy]\n\nSum it.", "sum_list", None, VISIBLE, None, "O(n)", "O(1)"
    )
    assert "SLUG: sum_list" in prompt
    assert '@reference("sum_list")' in prompt
    assert "@reference" in REFERENCE_SYSTEM
    assert "undecorated" in REFERENCE_SYSTEM.lower()


def test_an_undecorated_reference_is_repaired_not_refused():
    """The regression: an undecorated canonical solution must install, and the
    written source must carry the decorator (the file is the source of truth — a
    reference registered only in memory disappears on the next import)."""
    from dojo.curator.curator import _ensure_reference_registered

    ns = make_isolated_namespace()
    before_names, before_refs = set(ns), set(ns["REFERENCES"])
    exec(compile(UNDECORATED, "<reference sum_list>", "exec"), ns)

    source, note = _ensure_reference_registered(
        "sum_list", UNDECORATED, ns,
        before_names=before_names, before_refs=before_refs, function_name="sum_list",
    )
    assert "no decorator" in note
    assert ns["REFERENCES"]["sum_list"]([1, 2, 3]) == 6
    assert '@reference("sum_list")' in source
    # and the repaired source still runs, registering properly this time
    ns2 = make_isolated_namespace()
    exec(compile(source, "<reference sum_list>", "exec"), ns2)
    assert "sum_list" in ns2["REFERENCES"]


def test_a_wrong_slug_decorator_is_renamed():
    from dojo.curator.curator import _ensure_reference_registered

    ns = make_isolated_namespace()
    before_names, before_refs = set(ns), set(ns["REFERENCES"])
    exec(compile(WRONG_SLUG, "<reference sum_list>", "exec"), ns)
    assert "sum_list" not in ns["REFERENCES"]

    source, note = _ensure_reference_registered(
        "sum_list", WRONG_SLUG, ns,
        before_names=before_names, before_refs=before_refs, function_name="sum_list",
    )
    assert "different slug" in note
    assert ns["REFERENCES"]["sum_list"]([1, 2]) == 3
    assert '@reference("sum_list")' in source
    ns2 = make_isolated_namespace()
    exec(compile(source, "<reference sum_list>", "exec"), ns2)
    assert "sum_list" in ns2["REFERENCES"]


def test_an_unusable_response_names_the_real_cause():
    """The old message ('the reference disagrees with the oracle') pointed at the
    gate when the gate had not run — the wrong trail entirely."""
    from dojo.curator.curator import _ensure_reference_registered

    ns = make_isolated_namespace()
    before_names, before_refs = set(ns), set(ns["REFERENCES"])
    with pytest.raises(CuratorError, match="defines no usable entry point"):
        _ensure_reference_registered(
            "sum_list", "x = 1\n", ns,
            before_names=before_names, before_refs=before_refs, function_name="sum_list",
        )


def test_add_reference_installs_an_undecorated_model_response(sandbox):
    """End to end through `add_reference`, with the backend returning precisely
    what the live model returned."""
    overrides_path, registry_path, db_path, namespace = sandbox
    from dojo.db import connect

    with connect(db_path) as conn:
        conn.execute("UPDATE problems SET function_name = 'sum_list' WHERE slug = ?", (SLUG,))
        conn.execute(
            "UPDATE problems SET visible_tests = '[]' WHERE slug = ?", (SLUG,)
        )
        conn.commit()

    summary = add_reference(
        SLUG,
        MockBackend(referencer={"reference_code": UNDECORATED, "note": "sum()"}),
        overrides_path=overrides_path,
        registry_path=registry_path,
        registry_namespace=namespace,
        db_path=db_path,
        verify=lambda: (True, "verified"),
    )
    assert SLUG in namespace["REFERENCES"]
    text = registry_path.read_text()
    assert '@reference("sum_list")' in text
    assert "no decorator" in summary["note"]


# --------------------------------------------- class problems (min_stack shape)

CLASS_ORACLE = '''
@oracle("counter")
def _counter_oracle(ops: list[list]) -> list:
    value = 0
    out = []
    for op in ops:
        method, *args = op
        if method == "add":
            value += args[0]
            out.append(None)
        elif method == "get":
            out.append(value)
    return out
'''

CLASS_CASE = '''
@judge_case("counter")
def _counter_case(n, rng):
    ops = [["add", rng.randint(-5, 5)]]
    ops.append(["get"])
    return [], _counter_oracle(ops), {"ops": ops}
'''

#: What the model writes for a class problem: the class, not an op-list driver.
CLASS_REFERENCE = '''
class Counter:
    def __init__(self) -> None:
        self.value = 0

    def add(self, amount: int) -> None:
        self.value += amount

    def get(self) -> int:
        return self.value
'''


def test_a_class_reference_is_wrapped_in_the_op_list_driver():
    """`min_stack` is the curated set's one class problem, and its oracle follows
    the op-list convention while the natural (and student-facing) form is the
    class itself. Writing the class is not an error to reject — the judge harness
    already drives a class that way for the student, so the same driver is
    generated here."""
    from dojo.curator.curator import _ensure_reference_registered

    ns = make_isolated_namespace()
    exec(compile(CLASS_ORACLE, "<o>", "exec"), ns)
    exec(compile(CLASS_CASE, "<g>", "exec"), ns)
    before_names, before_refs = set(ns), set(ns["REFERENCES"])
    exec(compile(CLASS_REFERENCE, "<reference counter>", "exec"), ns)

    source, note = _ensure_reference_registered(
        "counter", CLASS_REFERENCE, ns,
        before_names=before_names, before_refs=before_refs, function_name="Counter",
    )
    assert "class" in note and "driver" in note
    assert "@reference(\"counter\")" in source

    # The wrapped reference answers the op list exactly as the oracle does.
    findings = reference_findings("counter", ns, [])
    assert findings == [], findings


# ------------------------------- the rollback may not delete real data (v0.13)
# `apply(overwrite=True)` is the only path `dojo report --fix` uses, and the
# rollback's delete asserted "the slug is guaranteed fresh, so no attempts can
# reference it" — false exactly there. With foreign keys on, the DELETE raised
# IntegrityError and so *replaced* the intended "rolled back" message with a
# foreign-key traceback; with foreign keys off it deleted the row out from under
# real attempts, which then vanished from history and from the ladder.


def _proposal():
    return {
        "slug": SLUG,
        "title": "Sum List",
        "difficulty": "Easy",
        "pattern": "arrays_and_hashing",
        "statement": "Sum List [Easy]\n\nSum it.\n\nYou should aim for O(n) time and O(1) space.",
        "function_name": "sum_list",
        "signature": "(values: list[int]) -> int",
        # `validate` wants 3-10 cases; VISIBLE has 2 (it is the gate fixture).
        "visible_tests": VISIBLE + [{"args": [[5, 5]], "expected": 10}],
        "oracle_code": ORACLE,
        "judge_case_code": GENERATOR,
    }


def test_a_failed_overwrite_rollback_keeps_a_referenced_row(sandbox, tmp_path):
    from dojo.curator.curator import apply
    from dojo.db import get_or_create_user

    overrides_path, registry_path, db_path, namespace = sandbox
    with connect(db_path) as conn:
        uid = get_or_create_user(conn, "andy")
        pid = conn.execute(
            "SELECT id FROM problems WHERE slug = ?", (SLUG,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, "
            "submitted_at) VALUES (?, ?, 'solve', 'correct', ?, ?)",
            (uid, pid, now(), now()),
        )
        conn.commit()

    problems_dir = tmp_path / "problems" / "arrays_and_hashing"
    problems_dir.mkdir(parents=True)
    (problems_dir / f"{SLUG}.py").write_text('"""Sum List [Easy]"""\n')

    with pytest.raises(CuratorError) as exc:
        apply(
            _proposal(),
            problems_dir=tmp_path / "problems",
            overrides_path=overrides_path,
            registry_path=registry_path,
            registry_namespace=namespace,
            db_path=db_path,
            verify=lambda: (False, "gate failed on purpose"),
            overwrite=True,
        )
    message = str(exc.value)
    assert "rolled back" in message          # the intended message...
    assert "FOREIGN KEY" not in message      # ...not a foreign-key traceback

    with connect(db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM problems WHERE slug = ?", (SLUG,)
        ).fetchone() is not None
        assert conn.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"] == 1
