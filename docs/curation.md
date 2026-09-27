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

## The corpus conventions (v0.14)

`dojo fetch --all` landed all 150 NeetCode-150 statements, but a landed statement is not a *curated* problem. This section is the contract for curating one by hand (or by agent), written down because 126 of the 150 were curated this way and the next 150 will be too. It is the recipe in AGENTS.md, made explicit for the shapes LeetCode uses and dojo does not.

### One rule above all: the statement's own examples are the anchor

A visible test that is not a transcription of an example in the problem's own statement is an opinion. `visible_tests` come from the statement's `Example` blocks — same inputs, same expected output — and everything else (oracle, generator, reference) is checked against them. A wrong visible test paired with a wrong oracle passes every gate dojo has, so the anchor has to be external to the code under test.

### Representations

dojo grades *functions over plain data*: the judge passes JSON values and compares JSON values. There is no `ListNode`, no `TreeNode`, no graph object — the reference and the student therefore share one calling convention, which is what makes the paired scale probe possible (the reference must run on the same inputs the student's code does). The mappings:

| LeetCode shape | dojo shape | Notes |
|---|---|---|
| `TreeNode` | nested list `[value, left, right]`, `None` = missing child | `(root: list \| None) -> int` |
| `ListNode` input | `list[int]` of node values | `(head: list[int]) -> list[int]` |
| `ListNode` with a cycle | index form: `next_node: list[int]`, `next_node[i]` = successor index, `-1` = null | a JSON list cannot contain a cycle; the index form is what Floyd's two pointers is *about* |
| `Node(val, next, random)` | `[[value, random_index], ...]`, `-1` = null | graded by the `deep_copy_valid` checker |
| graph adjacency | `list[list[int]]` (index-valued adjacency) | `clone-graph`, `graph-valid-tree` |
| edge list | `edges: list[list[int]]` plus `n` | connected components, redundant connection |
| grid | `list[list[str]]` / `list[list[int]]` | as the statement writes it |
| intervals | `list[list[int]]` | |
| design problem | `signature: {"methods": {...}}`, `function_name` = the class name, cases as `{"ops": [...], "expected": [...]}`, constructor args in `"ctor_args"` | `min_stack` is the worked example |
| design problem, parameterized constructor | as above **plus** `signature["ctor"]` (e.g. `"(self, capacity: int)"`), and a leading `["__init__", *ctor_args]` op in every case | `lru_cache`, `kth_largest_element_in_a_stream` |
| two collaborating functions | `signature: {"functions": {...}}`, `function_name` = the first one | `encode_and_decode_strings` |

Every statement that uses a LeetCode-only type gets a short **representation note** appended to it — "dojo passes the list of node values; return the same form" — because a student who reads `ListNode` in the statement and receives a Python list has been sent down a wrong trail.

**The known trade-off.** A list-backed linked-list problem can be "solved" with slicing (`head[::-1]`) instead of pointer manipulation. dojo accepts that: the grader's job is to grade honestly, not to enforce a technique, and the reviewer and the tutor see the code. The alternative — a `ListNode` runtime injected into the harness, the probe and the workbench — would give the reference and the student *different* calling conventions, which is the one thing the paired probe cannot survive. The index form covers the cases where the pointers are the problem (`linked-list-cycle`, `find-the-duplicate-number`).

### Verdict tags

| Tag | When |
|---|---|
| *(default, strict)* | one correct answer |
| `"compare": "sorted"` | the answer is a **set** of answers: subsets, permutations, combinations, palindrome partitions, letter combinations, word-search-ii, n-queens (the solution set is unique; only its order is free) |
| `"compare": "approx:1e-5"` | floats: median of two sorted arrays, `pow(x, n)` |
| `"compare": "mutates"` | LeetCode's "modify in place, return nothing": rotate-image, set-matrix-zeroes, walls-and-gates, reorder-list — `expected` is the **argument list after the call** |
| `"predicate": name` | the answer set is genuinely not unique (`valid_topological_order`, `valid_alien_order`, `longest_palindrome_valid`), the problem is a round-trip (`tree_codec_roundtrip`), or the contract is about identity (`deep_copy_valid`) |
| `{"ops": [...]}` | class problems |

A predicate checker receives `(module, got, args)` and must accept **every** correct answer — a checker that reimplements the oracle's tie-breaking turns a correct solution into a failed case (the `k_closest_points` trust bug, v0.12).

**Design problems carry two extra rules (v0.14).** A constructor that takes arguments is declared in `signature["ctor"]`, because the workbench stub is rendered from the signature: hard-coding `def __init__(self):` gave `LRUCache`/`KthLargest` students a stub of the wrong arity, which they met as a `TypeError` on their first `check`. And the *oracle and reference* never receive `ctor_args` — `curator._case_findings` calls them with the op list — so a parameterized constructor also travels as a leading `["__init__", *ctor_args]` op in every case, which the harness replays on the object it built from `ctor_args`. Both are asserted by `tests/test_registry.py` (`ctor_args` without a declared `ctor` is a failure).

### The four artifacts

1. **Statement** (`problems/<pattern>/<slug>.py`) — the fetched text, plus a representation note where a LeetCode type is involved, plus the corpus's complexity line: `You should aim for O(n) time and O(1) space.` `bank._COMPLEXITY_RE` parses that into `expected_time`/`expected_space`, which is what the submit-time complexity table compares the student's claim against — without it the column is blank for the whole corpus.
2. **`data/problem_overrides.json`** — `function_name`, `signature` (the stub the student fills in), `visible_tests` (transcribed examples), `lc_number`, and `probe_max_n` / `scale_compare` when the probe needs them (`probe_max_n` caps the largest measured input when the cost model only holds below some `n`; `scale_compare` is `"none"` for predicate-verdict problems, `"mutates"` for in-place ones, `"sorted"` for set answers).
3. **`judge/registry.py`** — `@oracle` (brute force, obviously correct), `@judge_case` (small random cases, `n` clamped to 0..12, values inside the statement's constraints, extras carrying the verdict tag), `@profiler_input` (worst-case-shaped inputs of size ~n — never early-exit inputs, and their *values* must respect the statement's constraints, not just their shape), and `@checker(name)` where a predicate is needed. Omit `@profiler_input` when measurement is meaningless (fixed-size inputs, exponential output).
4. **`@reference(slug)`** — a canonical, intended-complexity solution, admitted only by `curator.reference_findings` (agreement with the oracle on every visible and generated case, judged by the judge's own verdict modes). The reference is the probe's baseline: without it the probe still runs and reports failures at scale, but no growth verdict. Where the oracle *is* the intended algorithm the two are still written separately — the roles differ, and duplicating them keeps a brute-force oracle from silently becoming a performance baseline.

### The gate

`tests/test_registry.py` is the contract, and it is corpus-wide: overrides ↔ generators ↔ oracles ↔ references must agree, visible and generated cases must match their oracle, and every reference must pass `reference_findings`. Run `uv run pytest tests/test_registry.py` after every batch; a batch that leaves it red has not landed. With an API key, `dojo report <slug>` re-audits a curated problem through a fresh curator run plus the audit agent.

Three of its checks exist because the 126-problem batch needed them:

- **any** registered predicate checker is exercised on the oracle's own answer (the dispatch used to be a hardcoded `if/elif` chain, so a new checker name fell through to strict equality and was never run at all);
- **every** `@profiler_input` is executed at small n and its args must survive `json.dumps` — the generators otherwise run only inside a live session, where a raising one degrades to "no measurement" and says nothing (LC 74's called `math.isqrt` without importing `math`);
- **every** curated problem must render a template that compiles *and* an examples block, since `template_for` refuses to write a file that does not compile and the failure would reach the student as a session that will not start.

### Curating a batch offline, without an API key

The 126 remaining ladder problems were curated without a provider key: the same recipe, authored by hand (or by an agent) instead of by the curator model. The machinery is scratch tooling, not product code — it lived in the gitignored `data/curation/offline/` and is described here so the next corpus does not have to reinvent it:

1. **One fragment per problem** (`<group>/<slug>.json`): the statement additions (complexity line, representation note, or a full authored `body` for the six premium problems), the overrides entry, the registry block, the reference, and prose `notes` recording the judgement calls. Parallel authors never touch a shared file.
2. **An assembler** merges fragments into `problems/**`, `data/problem_overrides.json` and `judge/registry.py` idempotently — registry blocks are located through the AST by their decorators, references through their `# --- canonical reference (<slug>) ---` marker — and validates each fragment first (schema, roadmap group, decorator presence, no import of the injected decorators). Two of its rules came from bugs: a section scan that did not stop at the references header inserted blocks past the end of the file and then truncated them, and stripping the complexity line before the representation note duplicated the line on a second merge.
3. **A per-problem probe smoke** runs the oracle as the student against the reference across the probe's own ladder (the two must agree on the output, neither may fail), then exercises the reference alone at the largest measured size. `tests/test_registry.py` only proves agreement on *small* cases; this is where "the reference cannot handle n=6400" surfaces. Run it when the tree is quiet — it imports the registry, so a concurrent edit produces stale-source failures that look like reference bugs.
4. **Independent verification per batch**: an agent that did not write the fragments attacks the anchor (are the visible tests transcriptions of the statement's examples?), the contract, the oracle, the generator's constraints, the profiler input's shape, and any predicate checker in both directions, and writes findings as JSON. Its whole value is that the author's own self-check cannot catch a misunderstanding the oracle and the reference share.
