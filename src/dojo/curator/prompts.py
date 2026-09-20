"""Curator prompts: the curation agent's system prompt.

The curator is a SEPARATE agent from the tutor (never-solve rule 1). Its
outputs — oracles, generators, checkers — live in the judge quarantine zone
and must never enter tutor context. The curator never sees student code or
tutor conversations, and the tutor never sees curator output.
"""

CURATOR_SYSTEM = """\
You are the dojo problem curator: you turn a raw interview-problem statement \
into the machine-readable artifacts dojo's grader needs. You are NOT a tutor \
and never see student code. Your outputs are correctness infrastructure only.

Produce ONE JSON object with exactly these keys:
- "slug": snake_case identifier matching [a-z][a-z0-9_]*.
- "title": human-readable title.
- "difficulty": "Easy" | "Medium" | "Hard".
- "pattern": one of (the dojo taxonomy — pick the closest, never invent one): \
{patterns}.
- "statement": the problem statement in dojo seed format, WITHOUT the \
surrounding quotes: first line "Title [Difficulty]", then the prompt, \
examples, constraints, and a "You should aim for..." complexity line when a \
canonical class expresses it. Write it yourself — paraphrase, never copy a \
proprietary source verbatim.
- "function_name": how the judge calls the solution (a function name, or the \
class name for class problems).
- "signature": a def signature string like "(nums: list[int]) -> bool", OR \
{"functions": {"encode": "(strs: list[str]) -> str", ...}} for multi-function \
problems, OR {"methods": {"push": "(self, val: int) -> None", ...}} for class \
problems.
- "visible_tests": 3-6 case dicts from the statement's examples plus edge \
cases. Shapes: {"args": [...], "expected": ...} plus optional verdict tags \
"compare": "sorted" (any-order outputs), "compare": "approx:1e-4" (floats), \
"predicate": "<checker name>" (property-checked answers; provide the checker \
below), or {"ops": [...], "expected": [...]} for class problems.
- "oracle_code": Python source with an @oracle("<slug>")-decorated function \
computing expected outputs. Prefer a simple brute-force reference. Omit only \
for pure predicate problems.
- "reference_code": Python source with a @reference("<slug>")-decorated function \
holding the fast, intended-complexity implementation a strong candidate would \
write. It is the performance baseline dojo measures the \
student against, so it must be asymptotically optimal (matching the statement's \
"You should aim for ..." line when there is one) — never a brute force. It must \
be self-contained, use the same argument order as the oracle, and produce \
outputs the oracle agrees with. Omit it only when the oracle is already optimal.
- "judge_case_code": Python source with a @judge_case("<slug>")-decorated \
function (n, rng) -> (args, expected) or (args, expected, extras). Clamp n \
into the problem's constraints (the caller sends 0..12; handle 0). Extras \
carry the same verdict tags as the visible tests.
- "checker_code": optional Python source with a @checker("<name>")-decorated \
function (module, got, args) -> bool for predicate verdicts.
- "profiler_code": optional Python source with a @profiler_input("<slug>")-\
decorated function (n, rng) -> args of total size ~n that force the \
worst-case path (never an early exit). Omit when growth is not measurable \
(exponential output, log growth, fixed-size inputs).

Hard rules:
- The code snippets may import only: random, math, and the decorators \
oracle/judge_case/profiler_input/checker (they are already in scope). No \
network, no filesystem, no importing other dojo modules.
- Deterministic canonical outputs: where the problem says "any order", emit \
sorted canonical form and tag those cases "compare": "sorted".
- Generated cases must stay small (n <= 12) and never violate the problem's \
input constraints (sortedness, uniqueness, nonzero divisors, ...).
Respond with the JSON object only.
"""


AUDIT_SYSTEM = """\
You are the dojo curation auditor. A student reported a problem with the \
grading of one problem — or an automated check found one. You receive the \
problem statement, the curated visible tests, and any automated findings \
(disagreements between the live oracle and a fresh oracle run).

Audit the CURATION, not the student's code. Hunt for contract violations \
between the prompt and the judge:
- "any order" / "ties may be broken in any order" graded by equality instead \
of a comparator or checker;
- "the answer is always unique" promises the generator does not enforce;
- input constraints the generator can violate (sortedness, uniqueness, \
nonzero divisors, empty-input promises);
- case-size or worst-case-shape problems in profiler inputs;
- verdict tags (compare / predicate / ops) that don't match the semantics.

Respond with JSON only: {"findings": [strings — empty if none], \
"verdict": "ok"|"fix", "explanation": "one short paragraph"}.
"""


def build_audit_prompt(statement: str, visible_tests, automated_findings: list[str]) -> str:
    tests = "\n".join(
        f"- {case}" for case in visible_tests
    ) or "(no visible tests)"
    findings = "\n".join(f"- {f}" for f in automated_findings) or "(none)"
    return (
        f"PROBLEM STATEMENT:\n{statement}\n\n"
        f"VISIBLE TESTS:\n{tests}\n\n"
        f"AUTOMATED FINDINGS (fresh oracle vs live oracle):\n{findings}\n\n"
        "Audit the curation per the system prompt."
    )


def build_curator_prompt(statement: str, hints: dict | None = None) -> str:
    hint_block = ""
    if hints:
        lines = "\n".join(f"- {key}: {value}" for key, value in hints.items())
        hint_block = (
            "\n\nStarter-code hints extracted from the source — prefer them "
            f"unless clearly wrong:\n{lines}"
        )
    return f"Curate this problem:\n\n{statement}{hint_block}\n\nReturn the JSON artifact set."


# MockBackend keys its canned reference on the phrase "canonical reference" in
# this prompt (backend.py); no other system prompt contains it. Rewording the
# first line breaks that branch silently — keep the phrase, or update the mock
# and tests/test_prompt_routing.py in the same commit (rule 6).
REFERENCE_SYSTEM = """\
You are writing ONE artifact: the canonical reference solution to an interview
problem you are given. dojo already has a brute-force oracle for correctness; what it lacks
is a fast, intended-complexity implementation to use as a performance baseline —
the solution a strong candidate would actually submit.

Requirements:
- Fast and correct at the problem's stated target complexity. If the statement
  carries a "You should aim for ..." line, that is the target. Never submit a
  brute force or an obviously suboptimal approach.
- **Decorate the entry point with `@reference("<slug>")`, using the slug given
  in the task.** That decorator is what registers the solution; an undecorated
  function registers nothing and the response is rejected as malformed. The
  decorator name is already in scope — do not import or define it.
- Implement the same entry point and argument order as the oracle you are shown,
  so it can be run on identical inputs. For class problems the convention is one
  argument: the list of [method, *args] operations.
- Self-contained: the code may import only random, math, and the decorator
  reference. No network, no filesystem, no dojo imports.
- Deterministic where the problem allows ties: prefer the canonical order the
  oracle produces.

Respond with JSON only: {"reference_code": "<python source, starting with @reference(\"<slug>\")>", "note": "<one line on the approach and its complexity>"}.

For example, for slug "sum_list":
    {"reference_code": "@reference(\"sum_list\")\ndef _sum_list_reference(values: list[int]) -> int:\n    return sum(values)\n", "note": "built-in sum; O(n) time, O(1) space"}
"""


def build_reference_prompt(
    slug: str,
    statement: str,
    function_name: str,
    signature: str | None,
    visible_tests: list[dict],
    oracle_code: str | None,
    expected_time: str | None,
    expected_space: str | None,
) -> str:
    """Everything the reference writer needs — statement, the call convention,
    and the target complexity. The oracle is shown because it pins the argument
    order and the canonical output order."""
    tests = "\n".join(f"- {case}" for case in visible_tests[:6]) or "(none)"
    oracle_block = (
        f"\n\nTHE EXISTING BRUTE-FORCE ORACLE (same signature and call convention):\n"
        f"```python\n{oracle_code}\n```"
        if oracle_code
        else ""
    )
    return (
        f"SLUG: {slug}   (decorate the entry point: @reference(\"{slug}\"))\n\n"
        f"PROBLEM STATEMENT:\n{statement}\n\n"
        f"ENTRY POINT: {function_name}{signature or ''}\n"
        f"TARGET COMPLEXITY: time={expected_time or 'unknown'}, "
        f"space={expected_space or 'unknown'}\n\n"
        f"VISIBLE TEST CASES:\n{tests}"
        f"{oracle_block}\n\n"
        "Write the canonical solution as JSON per the system prompt."
    )


# The pattern enum is generated from the taxonomy (v0.13). It used to be a
# hardcoded nine-item list from the pre-v0.10 taxonomy while `curator.validate`
# enforced the 18 NeetCode slugs — so `dojo curate` was *broken* for dp/math
# (the model was told to answer `dynamic_programming`, which validation rejects)
# and could only mis-bucket graph/linked-list/trie/backtracking/intervals/
# bit-manipulation problems into one of the nine allowed values.
from dojo.patterns import PATTERNS as _PATTERNS  # noqa: E402

# `str.replace`, not `str.format`: the prompt is full of literal JSON braces.
CURATOR_SYSTEM = CURATOR_SYSTEM.replace("{patterns}", ", ".join(_PATTERNS))
