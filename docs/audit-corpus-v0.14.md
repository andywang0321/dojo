# Audit — the NeetCode 150 corpus (2026-09-27)

An audit of the *content* side of dojo (the roadmap ↔ bank ↔ registry
relationship, the landed statements, and what the daily loop can actually
serve), plus the work it started. The code audits are separate:
[docs/audit-v0.12.md](audit-v0.12.md) is the v0.12 one, and `roadmap/next.md`
carries the open findings from it. This document is about the 150 problems.

Method: read-only inspection of `data/roadmap.toml`, `data/problem_overrides.json`,
`problems/**/*.py`, `judge/registry.py` and the live `data/dojo.db`
(`mode=ro`), plus a simulation of `scheduler.pick_new_problem` against the live
attempt log. Numbers are as of `v0.13.0-9`.

## 1. What the bank contains

| | |
|---|---|
| Roadmap | 18 groups, **150** ladder problems, every LeetCode number unique |
| Bank | **161** rows = 150 ladder + 11 dojo-authored, every row has a seed file, no orphan rows, no duplicate `lc_number`, no missing `difficulty` |
| Curated | **29** rows — but only **24 on ladder slots**; the other 5 are dojo's own non-ladder problems |
| Remaining | **126 ladder problems landed but uncurated** |
| References | 28 of the 31 curated problems; `encode_and_decode_strings` and `min_stack` have none |

Two things explain the arithmetic. First, dojo's own seed corpus *owns* several
ladder numbers under its own slugs (`car_fleet` → LC 853, `daily_temperatures` →
LC 739, `three_sum` → LC 15, `two_sum_2` → LC 167, …), which is why
`arrays_and_hashing` (9/9), `two_pointers` (5/5) and `stack` (7/7) read as
complete. Second, everything else is a fetched statement with no overrides and
no registry block.

## 2. The finding that matters: the ladder is stuck after group 3

`scheduler.pick_new_problem` walks the roadmap in order and serves the earliest
unsolved *curated* ladder problem of the first eligible pattern. Curated ladder
coverage today:

| group | curated | group | curated |
|---|---|---|---|
| arrays_and_hashing | 9/9 | graphs | 0/13 |
| two_pointers | 5/5 | advanced_graphs | 0/6 |
| sliding_window | **0/6** | dp_1d | 0/12 |
| stack | 7/7 | dp_2d | 0/11 |
| binary_search | **0/7** | greedy | 1/8 |
| linked_list | **0/11** | intervals | **0/6** |
| trees | 1/15 | math_and_geometry | **0/8** |
| tries | **0/3** | bit_manipulation | **0/7** |
| heap | 1/7 | backtracking | **0/9** |

`sliding_window` is the first group with nothing curated, and the prereq gate
treats an empty group as satisfied (`next.md` #6, still open). So the gate does
not stop the student — it silently *skips* the group: the live session's next
pick is `valid_parentheses` (stack) even though `sliding_window` has never been
served. Solve the 7 stack problems and the ladder is exhausted; the fallback then
serves 5 non-ladder dojo problems and the loop reports "content exhausted" with
124 roadmap problems sitting uncurated in the bank.

## 3. Content defects in the landed corpus

* **6 problems are LeetCode-premium: the statement is a title and nothing else**
  (30 bytes of docstring). `Alien Dictionary [Hard]` is the whole problem. They
  are LC 252 meeting-rooms, 253 meeting-rooms-ii, 261 graph-valid-tree, 269
  alien-dictionary, 286 walls-and-gates, 323 number-of-connected-components.
  These need authored statements before they can be curated at all.
* **1 statement has no worked examples** (LC 371 sum-of-two-integers), so its
  visible tests have no external anchor.
* **No statement carries the complexity line** (`You should aim for O(…) time and
  O(…) space.`) that dojo's own seeds have, so `expected_time`/`expected_space`
  are NULL for all 126 and the submit-time complexity table's "expected" column
  is blank — the student's self-report is compared against nothing.
* **47 of 150 rows were filed in a pattern directory that disagrees with their
  roadmap group**, because `dojo fetch` buckets by LeetCode's *topic tags* and
  the roadmap's grouping is NeetCode's: `find-the-duplicate-number` is tagged
  "Two Pointers" and belongs to linked_list, `walls-and-gates` is tagged
  "BFS/DFS" and belongs to graphs, `meeting-rooms-ii` sits in two_pointers and
  belongs to intervals, `burst-balloons` sat in dp_1d and belongs to dp_2d.
  Ladder *picks* survive this (they match on `lc_number`) but everything that
  reads `problems.pattern` does not: `dojo list`'s grouping, `dojo progress`'s
  per-pattern proficiency, the card rollup key, learn-mode's `studied_patterns`
  and the unstudied-pattern offer, and the non-ladder fallback query.

## 4. Capability gaps that blocked curation

* **No provider key** in the environment or `.env`, and `data/curation/` empty —
  `dojo curate`, `dojo reference` and `dojo report`'s auditor cannot run, so the
  126 were curated offline (hand-authored, gated by the same tests).
* **No representation precedent** in the curated corpus for linked lists,
  graphs, tries or design problems: none of the 31 curated problems touch them.
  Curating 126 problems therefore required pinning the corpus-wide conventions
  first — now written down in [docs/curation.md](curation.md#the-corpus-conventions-v014).
* **In-place problems had no verdict mode.** LC 48 rotate-image and 73
  set-matrix-zeroes say "modify in place, return nothing"; the judge compared
  return values only, so a faithful solution would have been graded wrong.

## 5. What this work changed (structural, before any content)

1. **A `"compare": "mutates"` verdict mode** (`judge/compare.py:case_verdict`,
   the harness, the curator's reference gate, `tests/test_registry.py` — one
   implementation, four callers): `expected` is the argument list as it must
   stand after the call, and a rebinding `matrix = <new list>` fails. The scale
   probe digests the same effect rather than two identical `None`s, and the
   workbench renders a runnable examples block for it.
2. **The 47 mis-filed seed files moved** into their roadmap group directories
   (`git mv` + reseed — the row's `pattern` follows the file's directory), so
   `problems.pattern` now agrees with the roadmap for all 150. No attempt or card
   referenced any of the moved slugs, so nothing was lost.
3. **The fetcher now consults the roadmap**: both `dojo fetch <slug>` and
   `dojo fetch --all` override the tag-derived pattern with
   `cli._roadmap_groups_by_lc()[lc]` before landing, so the drift cannot come
   back on the next fetch.
4. **The corpus conventions are documented** (docs/curation.md), including the
   representation table for linked lists, graphs, design problems and in-place
   problems, and the rule that a problem's visible tests are transcribed from its
   own statement's examples.

## 6. The curation itself

The 126 remaining ladder problems are curated in roadmap order, one group per
batch, each batch gated by `tests/test_registry.py` (corpus-wide: overrides ↔
generators ↔ oracles ↔ references must agree) and committed on its own. Per
problem the batch produces: the statement's complexity line + representation
note, the `problem_overrides.json` entry, the `@oracle` / `@judge_case` /
`@profiler_input` set, and a `@reference` admitted by `curator.reference_findings`.

Three pieces of tooling made that tractable, and all three found real defects
before anything landed (they live in the gitignored `data/curation/offline/` —
scratch, like the curator's own proposals):

* **Fragments + `assemble.py`** — one JSON file per problem, written
  independently so authors never touch a shared file, merged into the three
  artifacts idempotently (registry blocks found through the AST, references
  through their marker comment, statements and overrides keyed by slug).
* **`probe_smoke.py`** — per problem, oracle-as-student vs the registered
  reference across the probe's ladder, plus a reference-vs-itself run at the
  largest measured size. `tests/test_registry.py` only proves agreement on small
  cases; this is where "the reference cannot handle n=6400" or "the profiler
  input makes the two disagree" shows up, and it caught LC 74's generator calling
  `math.isqrt` without importing `math` — a `NameError` that a live session would
  have reported as "no measurement" and nothing else.
* **The corpus-wide profiler-input smoke** in `tests/test_registry.py`
  (generators must run and their args must survive `json.dumps`) — the permanent
  version of the same check.

Two findings came out of the content work rather than the code:

* **A sub-linear reference could not support a "better" claim.** Against an
  `O(log n)` reference the whole `O(1)` → `O(log n)` step spans ~1.9x over the
  ladder — the same magnitude as a constant-factor advantage — so a correct
  student calling the C-implemented `bisect` was named "better — O(1)" in 5 of 8
  runs while both sides did the same logarithmic work. `growth.verdict` now
  returns `unresolved` for the improvement direction against a sub-linear
  declared class, keeping the worse direction (a linear scan against a log
  reference is ~60x) decidable.
* **Two legacy complexity lines did not parse** (`min_stack`,
  `encode_and_decode_strings`): the statement-shaped `O(1) time and O(n) space`
  adjacency is what `bank._COMPLEXITY_RE` reads, and both interpolated words
  between the two halves, so their Expected column had always been blank.

Status (each group is committed once assembled, gated and probe-smoked):

| group | problems | status |
|---|---|---|
| sliding_window | 6 | ✓ committed, verified |
| binary_search | 7 | ✓ committed, verified |
| tries | 3 | ✓ committed, verified |
| linked_list | 11 | ✓ committed, verification running |
| trees | 14 | ✓ committed, verification running |
| heap | 6 | ✓ committed |
| backtracking | 9 | ✓ committed |
| bit_manipulation | 7 | ✓ committed |
| math_and_geometry | 8 | ✓ committed |
| intervals | 6 | ✓ committed |
| greedy | 7 | ✓ committed |
| graphs | 13 | ✓ committed (3 premium statements authored) |
| advanced_graphs | 6 | ✓ committed (1 premium statement authored) |
| dp_1d | 12 | ✓ committed |
| dp_2d | 11 | ✓ committed |

**All 150 ladder problems are curated** (up from 24 when this audit started), the
suite is 562 passing, and `dojo roadmap --table` no longer skips a group —
`sliding_window` became the ladder's next group the moment its six problems
landed, where before the prereq gate treated the empty group as satisfied and
served a later ladder instead.

## 6c. Known limits this batch left behind

Recorded rather than hidden, because each is a real narrowing of what dojo can
claim about a solution:

* **A predicate checker cannot see the pre-call arguments.** The harness hands
  checkers `(module, got, args)` with `args` in its post-call state, so
  `deep_copy_valid` / `graph_copy_valid` cannot catch a student who mutates the
  input and then copies the damaged values — the copy IS faithful to what the
  input now holds. The scale probe does catch that shape (its digest is the
  input), and closing it in the judge needs the pre-call arguments passed to
  checkers, which is a harness change.
* **Probe inputs are bounded by the oracle's in-process cost.** `_oracle_confirms`
  runs the oracle with no timeout of its own, so several profiler inputs carry a
  `probe_max_n` below the statement's own bound (walls-and-gates 1600, burst-balloons
  150 — the latter because the probe's tracemalloc phase is superlinear). Where the
  input could stay at the statement's bound without that risk, it does.
* **Growth verdicts are direction-only for multi-variable classes.** A line like
  `O(n + e)` or `O(m * n)` is not one of the classes `growth.verdict` can name, so
  those problems report a ratio and a direction with the Measured column reading
  "unresolved" — honest, but it means a correct solution to a graph problem gets
  no class confirmation.
* **Two O(log n) problems needed the sub-linear guard to stay honest** (LC 704/74
  keep their inputs; LC 33/153 got theirs back only after the guard landed), and
  `longest-increasing-subsequence`'s O(n log n) reference measures nearly linear
  because `bisect` is C: a quadratic student's trend is clearly worse (20-60x above
  a same-class control) but the class label does not resolve on a 2,500-element
  ladder.
* **A missing `function_name` in the probe reads as "no measurement" rather than
  a failure** — the probe harness's outer `try` has only a `finally`, so an
  AttributeError there yields an all-`None` payload. Reported by an author; not
  fixed here.

## 6b. What the batches turned up in the product

Curating 126 problems exercised paths the 31-problem corpus never had, and each of
these is a fix that landed with the content:

* **Class stubs with constructor arguments.** `render_template` hard-coded
  `def __init__(self):`, so `LRUCache`/`KthLargest` stubs had the wrong arity and a
  student filling them in met a `TypeError` on their first `check`. `signature["ctor"]`
  now carries the parameters, and `tests/test_registry.py` fails a class problem
  whose cases pass `ctor_args` without declaring one.
* **The oracle/reference side of a design problem.** `curator._case_findings` calls
  them with the op list only, so a parameterized constructor has to be replayed as a
  leading `["__init__", *ctor_args]` op — two authors invented the same convention
  independently, and it is now documented.
* **`_oracle_confirms` was vacuous under `"mutates"`**: it compared two `None`
  returns, so the "the oracle confirms the mismatch" line confirmed anything,
  including a mismatch caused by a broken reference. Each side now gets its own
  deepcopy and the mutates mode compares the arguments left behind.
* **`_case_findings` consumed the caller's case objects** for an in-place reference,
  so a second gate call on the same list reported a false finding.
* **Two complexity lines never parsed** (`O(max(m, n))`, `O(4^n / sqrt(n))`):
  `bank._COMPLEXITY_RE` now accepts one level of nested parentheses, so the Expected
  column is populated for the two statements that had been blank since they were
  written.
* **A profiler input that clamps below the ladder top** measures the identical input
  at every size above the clamp, flattening the ratio series by construction — a
  deliberately quadratic solution read as "matches" (found by an author on their own
  fragment, then swept corpus-wide; the two affected fragments now carry a matching
  `probe_max_n`).
* **A generator that could not run**: LC 74's called `math.isqrt` without importing
  `math`, and LC 287's raised `ValueError` on a legal size. The first is now caught
  corpus-wide by a profiler-input smoke in `tests/test_registry.py`; the second by
  the registry gate it turned red.
* **The verifiers' own findings** were folded in rather than logged: LC 212's
  generator only emitted square boards and LC 211's dotted queries only ever had an
  added word's length (both now vary); the tries batch's committed registry drifted
  from its fragment (the assembler is the only writer, and re-assembly is
  byte-idempotent).

## 7. What this audit did not do

* **No curriculum work.** `roadmap/v0.14.md`'s Increment 1 (the curriculum seam)
  is untouched; this is the content gap that stage explicitly refused to let
  block it ("the curriculum work must not be an excuse to leave the ladder
  permanently stuck at 24 rungs").
* **The prereq gate still degrades on an empty group** (`next.md` #6). While 126
  ladder problems were uncurated, an empty group correctly meant "nothing
  curated here yet"; the gate cannot tell that from "finished". It is left as
  found, and named here because it is the mechanism by which the stall stayed
  invisible.
* **`problems.source` is still a dead column** (`next.md` #13): all 161 rows say
  `seed`, including the 150 fetched ones, so which statement was fetched and
  which was authored is not recoverable from the DB. It is recoverable from
  git — the six authored statements are in this audit's commits.
