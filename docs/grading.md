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

## The profiler

For each of `[100, 200, 400, 800, 1600, 3200, 6400]`, the function runs on worst-case-shaped inputs: 5 repeats per size, median per size, one measurement per subprocess (the subprocess boundary contains hangs — never replace it with in-process timing). Inside each subprocess three calls run, in this order:

1. an untimed warm-up call, which resolves first-call bytecode specialisation before anything is measured;
2. **the timed call, with no tracer running** (GC disabled);
3. the space call, with `tracemalloc` active and no timer.

Each call gets a fresh deep copy of the arguments, so a solution that mutates its input in place cannot make later calls do different work than the first.

**Why the order matters (v0.11).** `tracemalloc` used to be started *before* the timed call. Its per-allocation bookkeeping is itself superlinear, so the "time" being measured included the instrument: on one real solution the log-log slope was **1.164 with tracing and 0.889 without** — the difference between reporting O(n log n) and O(n). It misclassified 8 of the 15 measured attempts in the live database, and in all 8 the student's claim agreed with the problem's own documented expected class, so the measurement was the only outlier. Replaying those same solutions through the fixed protocol produces **0 disagreements**.

### The decision rule

Each candidate class f is fitted to the measurements as `y = k·f(n) + c` by least squares, and every candidate whose residual stays within the measurement's own noise of the best residual is **plausible**. The report is the simplest plausible class plus a **bracket** naming what the data cannot tell apart:

```
Time    O(n log n)    O(n log n)    O(n)…O(n log n)    0.998
                                    cannot separate O(n) from O(n log n)
```

This replaced an R² comparison plus a magic log-log slope threshold (`NLN_SLOPE_THRESHOLD = 1.06`). That threshold sat *above* the slope actually measured for a genuine O(n log n) function (1.005–1.030 over four trials, biased low by the additive overhead every measurement carries), so sort-based solutions were classified O(n) every time — while the tracemalloc contamination pushed allocation-heavy linear code the other way. Two errors cancelling made the output look plausible.

The deeper reason a threshold cannot work: over this probe ladder the O(n) and O(n log n) shapes differ by only ~0.3% of the signal variance, below realistic timing noise (the measured per-point spread is 3–12%). They are not separable by fit quality at that noise, and the honest output is a range — not a guess. Coarser distinctions (n vs n², n² vs n³) separate by orders of magnitude and are still reported as single classes with confidence.

The guarantee is tested rather than asserted: across a noise sweep of 0–30% over all five candidate shapes, the classifier never returns a single wrong class (it brackets instead). Those tests are synthetic and deterministic — the old suite asserted a *measured* class and flaked under load, which tests the machine rather than the rule.

Two safeguards survive from earlier stages: the **allocator staircase** fix (space fits use every second point — `fit.staircase_safe_points`: set/dict tables are power-of-two staircases that alias a linear structure as O(n²) at exact doublings), and the R² < 0.9 "treat class as suggestive" flag.

### Comparison is three-valued

`complexity.compare` returns **agree**, **disagree** or **incomparable**, and the table renders all three. The previous two-valued version silently dropped any class outside its canonical table: `O(n+m)`, `O(n*m)` and `O(k)` were unknown, so a student's `O(n+m)` claim produced *no* mismatch against a measured `O(n^2)` — a confident blank where the widest disagreement in the book should have been. Multi-parameter expressions are canonicalized (`O(n+m) ≡ O(m+n)`, `O(n*m) ≡ O(m*n)`), and an axis whose sides are not comparable says so instead of staying silent. A claim inside the measurement's bracket is not a disagreement, so a bracketed reading no longer reddens a correct claim.

## The reviewer

Post-submission, rubric-scored JSON: correctness, approach quality, style/idiom, naming, edge cases, complexity-claim check, **complexity-reasoning** (is the *why* behind the claim sound?), plus **reflection feedback** (prose on the student's reflection — feedback, not a score), broader picture, overall comment. Inputs: statement, submitted code, self-reported complexity (the raw strings, so the reasoning is visible), measured complexity, expected complexity, the static-analysis block, and the student's reflection — which is why reflection now happens *before* the review.

The reviewer also receives a **measurement confidence** line (R², plus whether the reading was bracketed or low-confidence) with the instruction that such a measurement is not evidence against the student's claim. It used to be handed a bare class and left to guess: in the live data it consistently defended students against the tool's own contaminated measurements ("the empirical measurement of O(n log n) is almost certainly an artifact of the benchmark harness"), which meant the AI layer was silently error-correcting the deterministic one. Making the measurement honest is the fix; telling the reviewer is the belt-and-braces.

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
