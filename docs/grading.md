# Grading: judge, profiler, reviewer, static analysis

## The judge

Student code runs in an isolated subprocess with a JSON protocol: the harness imports the workbench file, calls the problem's function, applies the case's verdict mode, and kills on timeout. Cases come from three layers: visible examples (curated in `data/problem_overrides.json`), randomized generated cases, and oracle-checked cases where a brute-force reference exists (`judge/registry.py`). Oracle and checker code is correctness infrastructure only — never tutor context.

### Verdict modes (per case)

- `strict` (default): JSON equality with `sort_keys`. No leniency — a non-serializable return fails the case.
- `"compare": "sorted"` — deep-sorts both sides before equality; the honest way to support "any order" prompts.
- `"compare": "approx:1e-4"` / `"compare": "rounded:n"` — recursive float tolerance / rounding.
- `"predicate": name` — a `@checker(name)` in the registry validates `(module, got, args)`; for round-trips, any-valid-sample, any-peak, and any-valid-k-closest-set (boundary distance ties: the checker accepts any valid tie choice — equality judging there once false-failed correct solutions, the trust bug).
- `{"ops": [...], "expected": [...]}` — class problems: instantiate `function_name`, replay the method sequence, compare per-op outputs.

### Registries (`judge/registry.py`)

- `@oracle(slug)` — correctness reference (prefer brute force).
- `@judge_case(slug)` — `(n, rng) -> (args, expected[, extras])`. Clamp n into the problem's constraints (the caller sends 0..12); extras carry the same verdict tags as the visible tests.
- `@profiler_input(slug)` — `(n, rng) -> args` of total size ~n that force the worst-case path.
- `@checker(name)` — predicate verdicts.

The random-bracket lesson: a *random* bracket string fails at the first unmatched closer, which would make an O(n) solution measure as O(1). Profiler inputs must be worst-case-shaped — `valid_parentheses` uses n nested opens followed by n closes.

## The scale probe (v0.12)

The profiler is no longer a complexity classifier. It runs the student's code at
increasing sizes and reports two things it can actually establish:

1. **Failure at scale.** An exception or timeout on a worst-case-shaped input,
   with the size and the message. This is the only place dojo runs user code
   above n ≈ 12 — the judge's generated cases are `n = randint(0, 12)` by design —
   and it is the thing that caught a real `ValueError` that the AI reviewer had
   scored 5/5 on correctness.
2. **Growth, relative to the canonical reference solution.** Both implementations
   run interleaved at each size, so machine drift is common-mode and the *ratio*
   cancels every constant factor they share: interpreter overhead, cache
   behaviour, allocator staircases.

### Why not an absolute fit

v0.11 fitted a single cost curve and named a class. That cannot work, and the
numbers are not close: over a feasible ladder (n = 100 … 6,400) O(n) and
O(n log n) differ by **~0.3% of the signal variance** while the measured
per-point spread is **3–12%**. The honest output was therefore a bracket —
`O(n)…O(n log n)` — which is not useful enough to be worth the machinery.

The levers that look like they should fix it do not. Extending the ladder from 6
to 14 doublings (n up to 1.6 million — infeasible for any quadratic solution)
moves the noise the rule can tolerate from 4.06% to 3.48%. Quintupling the
repeats moves the observed spread from 6.6% to 5.9%, because the residual
variance is *systematic* (CPU state, cache, memory layout), not sampling error.

Comparing against a reference removes the problem instead of fighting it. The
same implementation on both sides gives a flat ratio (measured trend 0.87–1.04
over repeated runs); quadratic code against a linear reference gives a trend of
~64. The library that does this the absolute way, `big-O` (used by
`python-zipp`), has the same ceiling — its own documentation example separates
Linear from Linearithmic by a factor of 2.5 in residuals, and its most serious
user treats the result as a bound and marks the tests flaky.

### The verdict

The ratio trend is matched against the trends the candidate classes would
produce, anchored on the problem's declared complexity, so the answer is a class
*relative to the reference*:

| kind | meaning |
|---|---|
| `matches` | grows like the reference — consistent with the target class |
| `worse` / `better` | N classes above/below it, with the ratio that says so |
| `unresolved` | the ratio matches no class closely enough — reported as such, never rounded to one |
| `failed` | the code broke at scale; the size and message are the finding |
| `unreferenced` | no reference registered, so growth was not compared |

`tests/test_growth.py` pins the rule on synthetic ratio series derived from real
class pairs — including the counter-case (n^1.5, which sits between n and n² and
must come back unresolved) — and never from wall-clock timing. Adding a
reference is gated: see `curator.reference_findings`.

### Probe protocol

Per (size, repeat), one subprocess per target, interleaved:

1. an untimed, untraced warm-up call;
2. **the timed call with no tracer running** — and with the argument copy made
   *outside* the timed window (v0.11 put it inside: at n=6400 the deepcopy was
   0.769 ms of the 1.005 ms reported, so 76% of the "algorithm time" was the
   profiler's own bookkeeping);
3. the space call with `tracemalloc` active and untimed;
4. the result reduced to a digest, so an output that disagrees with the
   reference is noticed for free.

An exception or timeout stops the ascent (bigger is pointless once it breaks) and
skips the remaining repeats of a timed-out size. The ladder is capped per problem
by an optional `probe_max_n` override, and the output comparison mode comes from
`scale_compare` (`strict` by default, `sorted` for order-insensitive answers).

Space no longer needs the `staircase_safe_points` subsample from v0.8.1: a
staircase in the container sizes appears in *both* curves and cancels in the
ratio.

## The reference

`ORACLES` and `REFERENCES` are different artifacts with different jobs
(`judge/registry.py`):

- **oracle** — brute-force correctness anchor. Deliberately simple, because an
  obvious implementation is one you can trust. It cannot double as a performance
  baseline (it *is* the slow thing: `products_of_array_except_self` targets O(n)
  while its oracle is an O(n²) double loop) and it cannot run at scale at all.
- **reference** — canonical, intended-complexity solution. The probe's baseline.
  Admitted only when it agrees with the oracle on every visible test and
  generated case, judged by the judge's own verdict modes; `tests/test_registry.py`
  re-runs that gate over the whole corpus so a drifted reference cannot survive CI.

## The reviewer

Post-submission, rubric-scored JSON: correctness, approach quality, style/idiom, naming, edge cases, complexity-claim check, **complexity-reasoning** (is the *why* behind the claim sound?), plus **reflection feedback** (prose on the student's reflection — feedback, not a score), broader picture, overall comment. Inputs: statement, submitted code, self-reported complexity (the raw strings, so the reasoning is visible), measured complexity, expected complexity, the static-analysis block, and the student's reflection — which is why reflection now happens *before* the review.

The reviewer also receives the probe's **verdict and its strength** (the ratio trend, and whether the reading was resolved, unresolved, or the code failed at scale) with the instruction that an unresolved measurement is not evidence against the student's claim. It used to be handed a bare class and left to guess: in the live data it consistently defended students against the tool's own contaminated measurements ("the empirical measurement of O(n log n) is almost certainly an artifact of the benchmark harness"), which meant the AI layer was silently error-correcting the deterministic one. Making the measurement honest is the fix; telling the reviewer is the belt-and-braces.

Hard rules: it critiques, never repairs — no alternative solutions, no code. Terminal-safe: plain text only, `de_markdown` applied at display time (underscores are never stripped — they may be identifiers like `two_sum`).

Model output is schema-normalized (`reviewer.normalize_review`) before display and storage: rubric dimensions may arrive as `{"score", "comment"}` dicts or as bare numbers, and either shape must render (a real solve once returned bare ints and the chart came out empty). Scores are clamped to the 1–5 rubric (a 10-point-scale model once shipped 9/5 scores; the prompt now states the scale too), and a transient non-JSON response gets one retry before the review is skipped (a real first-submit review once died this way).

## Static analysis (v0.4, advisory since v0.6)

Runs at **every `check`** as advisory findings (radon cyclomatic complexity per function + ruff), so the student can fix them before the reviewer ever sees the code — the trainer-not-exam stance: the style score grades the final submitted code, and the live loop itself teaches the habit. Submit still stores the analysis (`static_analysis` JSON) and feeds it to the reviewer as evidence ("reference it where relevant — never invent findings"). Complexity above the McCabe convention (10) is a flag, never a failure; tool hiccups degrade into `notes`.

## The post-solve loop (v0.6)

After review + reflection, the session continues with `polish` (re-judge + re-measure + re-analyze the edited code, updating the same attempt row and bumping its `polished` counter; an optional second review), `discuss <question>` (free post-solve chat — the never-solve boundary lifts after solving; the transcript persists on the attempt row), and `done` (retire the state).

## The report command (v0.7)

`dojo report [slug]` (and in-session `report`) audits a problem's *curation*, not the student's code: it runs a fresh curator pass, cross-checks the fresh oracle against the live one on generated cases, then asks the audit agent to hunt prompt-vs-judge contract violations (ties graded by equality, "unique answer" promises the generator doesn't enforce, constraint fidelity, verdict-tag mismatches). Findings land in gitignored `data/curation/<slug>.report.json` and print to the terminal; `dojo report --fix <slug>` re-curates through the dual-oracle pipeline + verification gate when the verdict is "fix" (the new registry block wins at import; rollback restores the original files, overrides, and registrations).

## Per-pattern score trends (v0.4)

`db.review_trends` aggregates the reviewer's rubric per pattern with recency-linear weighting (the oldest of n attempts weighs 1, the newest n). Rendered as the "Score trends per pattern" table in `dojo progress`. Missing or malformed reviews are skipped.

## Verdicts and containment (v0.13)

`run_cases` returns one of four statuses, and they mean different things:

| Status | Meaning |
|---|---|
| `correct` | every case passed |
| `wrong_answer` | every case *ran*; at least one value disagreed |
| `error` | at least one case raised (or the harness itself could not run) — a crash is not a wrong answer, and the two need different coaching |
| `timed_out` | the wall clock expired; per-case results are unavailable |

An **empty case list is refused** (`status="error"`, label `no cases`): `all_passed`
is true for zero cases, so a problem with neither visible tests nor a generator
used to be a free solve. A problem is curated only when its `visible_tests`
*parses* to a non-empty list — the old guard tested the truthiness of the JSON
string, so `"[]"` slipped through.

Containment, in the parent's hands (`dojo/proc.py`): user output is collected
into temp files and read back capped (a print loop used to reach ~1.9 GB of RAM
in three seconds, and the *probe* could grow dojo's own memory to 1.75 GB by
capturing the stderr it routes prints to); the child runs in its own session and
its whole process group is killed on timeout (a spawned grandchild once outlived
a `timed_out` run); the harness sets address-space, file-size and CPU limits on
itself; and the result is read as the last parseable line, so a late print from a
thread or an `atexit` handler cannot corrupt the protocol.

The student's code still executes in the same process as the harness, so it can
in principle patch the comparators and rewrite its own verdict. That is a
deliberate trade — dojo is a private two-person tool and the judge is not a
security boundary — but it is worth knowing that `import dojo` from a solution
also exposes the oracles. Do not describe the subprocess as a sandbox.
