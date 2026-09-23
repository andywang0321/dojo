# The problem bank and curation

## The bank

Every problem has a **slug** (stable machine identifier: the filename stem), a **title** (human-readable name), and a statement. `dojo init` imports every `problems/**/*.py` file whose module docstring starts with `Title [Difficulty]` (pattern = parent directory; expected complexity is parsed from the "You should aim for O(...) time and O(...) space" line when present). Seeding is an upsert on slug — it never deletes rows that attempts reference.

Patterns live in `dojo/patterns.py` — the single source of truth shared by the bank and the curator:

`arrays_and_hashing, two_pointers, sliding_window, stack, binary_search, linked_list, trees, tries, heap, backtracking, graphs, advanced_graphs, dp_1d, dp_2d, greedy, intervals, math_and_geometry, bit_manipulation` (the 18 NeetCode groups in roadmap order — v0.10)

**Curated** is a stricter bar — the ✓ column in `dojo list`. A problem is curated when it has everything `dojo day` needs:

1. `function_name` + `visible_tests` + a template `signature` in `data/problem_overrides.json` (a string for one function, `{"functions": {...}}` for multi-function problems, `{"methods": {...}}` for class problems);
2. a `@judge_case` generator + `@oracle` in `judge/registry.py` (or `@checker`-based predicate cases) and, wherever measurement is meaningful, a `@profiler_input`.

Trees use the nested-list representation `[value, left, right]` (`None` = missing child / empty tree), documented in the tree prompts. `tests/test_registry.py` pins the whole contract: overrides, signatures, oracles, checkers, and generators cover exactly the same slug set; every visible test and generated case agrees with its reference; representative references pass through the real judge subprocess.

## The canonical reference

Every curated problem may also carry a **reference**: a fast, intended-complexity
solution used as the scale probe's baseline. The brute-force oracle cannot serve
that role (it is the slow thing, and it cannot run at scale), so the reference is
a second artifact with its own admission rule — it is installed only if it agrees
with the oracle on every visible test and generated case, judged by the judge's
own verdict modes. `dojo reference <slug>` generates one for an existing problem;
`dojo reference --all` backfills the bank. A refused reference writes nothing.
The prompt gives the model the problem's slug and requires `@reference("<slug>")`
on the entry point; a response that omits it (or decorates with a different slug,
or answers a class problem with the class rather than the op-list driver) is
repaired rather than refused — `curator._ensure_reference_registered` — and the
repair is written into the source, since the file is what the next import reads.

## `dojo curate` — the AI curation pipeline

Paste a statement (`dojo curate`, or `--text` / `--file`), and the curator agent — structurally separate from the tutor — generates the full artifact set:

1. **Propose twice** (dual-oracle differential): two independent curator runs, each producing slug, title, difficulty, pattern, statement (paraphrased, with a complexity line where canonical), function_name, signature, visible_tests, oracle/generator/checker/profiler code.
2. **Differential check**: both proposals are executed in isolated namespaces and the two oracles are cross-checked on the generated cases under strict equality. Any disagreement rejects the proposal — the oracle is the trust root.
3. **Apply with rollback**: the seed file, overrides entry, and registry block are written; the verification gate (`tests/test_registry.py`) runs; any failure rolls back files, DB row, and in-memory registrations.

Proposals are kept in `config.CURATION_DIR` (gitignored `data/curation/` — user state, so it follows `DOJO_DATA_DIR`) for provenance. Human curation still works — the recipe is the same, the gate is the same.

## Model-written code is repaired, never fatal (v0.13 follow-up)

A proposal's code fields are executed twice before anything is written (the dual-oracle differential, then the apply step), so a *shape* the model gets wrong is a curation failure — and one shape got through badly: the prompt's import rule ("may import only: random, math, and the decorators") was read literally as an instruction to write `from decorators import oracle`. The decorators are **injected** into the exec namespace; there is no `decorators` module, so the snippet raised `ModuleNotFoundError`, which escaped `audit_curation` and killed a live session mid-solve (2026-09-23).

Two fixes, deliberately at different levels:

- **The prompt says the truth**: the decorators are already in scope, and an import for them is a hard error — stated for the curator and for the reference writer (both had the same inviting wording).
- **`curator.sanitize_imports` repairs the shape** (the same stance as `_ensure_reference_registered` and `reviewer.normalize_review`): any import statement the isolated namespace cannot satisfy is dropped, real modules (`heapq`, `typing`, `collections`) are kept, and line numbers are preserved so a traceback inside the snippet still points at the right line. What was stripped is announced — as `_repairs` on the proposal, in the reference's one-line note, and as an automated finding in the audit — because a model that keeps misreading the rule is evidence about the prompt, not noise to hide.

Everything else about model-written code is a boundary: `_exec_proposal` raises `CuratorError` (naming the field and the original exception) instead of leaking whatever the snippet raises, and `_backend_json` already wraps transport failures. The in-session `report` sits behind `dojo.guard` on top of that, so no curator failure of any kind can end a student's session.

## `dojo fetch` — LeetCode intake (v0.3)

`dojo fetch <title-slug>` pulls a problem from LeetCode's GraphQL API: content HTML → plain text (stdlib `HTMLParser`; superscripts become `^`, so `10^4` doesn't render as "104"), topic tags → pattern via `patterns.py` (unmapped tags fail loudly rather than landing in a wrong bucket), and the python3 starter snippet → `function_name` + `signature` hints (annotations normalized to builtin generics, class snippets become `{"methods": {...}}`). The statement lands uncurated, then auto-curation runs through the same pipeline; if the curator fails or no API key is set, the statement stays in the bank (`—` in `dojo list`) for a later `dojo curate --file`.

The HTTP transport is an injected callable: tests pin the contract against canned GraphQL fixtures and never hit the network. The live endpoint is unversioned, so schema drift surfaces as a `LeetCodeError`, never a silent half-fetch.

## Copyright

Private use: dojo serves two PhD students' private practice. Statements, visible tests, and other data may draw on public sources (LeetCode, books) and live in the bank as normal; the repo stays private — never publish the bank or its data.
