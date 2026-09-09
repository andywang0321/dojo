# Grading: judge, profiler, reviewer, static analysis

## The judge

Student code runs in an isolated subprocess with a JSON protocol: the harness imports the workbench file, calls the problem's function, applies the case's verdict mode, and kills on timeout. Cases come from three layers: visible examples (curated in `data/problem_overrides.json`), randomized generated cases, and oracle-checked cases where a brute-force reference exists (`judge/registry.py`). Oracle and checker code is correctness infrastructure only — never tutor context.

### Verdict modes (per case)

- `strict` (default): JSON equality with `sort_keys`. No leniency — a non-serializable return fails the case.
- `"compare": "sorted"` — deep-sorts both sides before equality; the honest way to support "any order" prompts.
- `"compare": "approx:1e-4"` / `"compare": "rounded:n"` — recursive float tolerance / rounding.
- `"predicate": name` — a `@checker(name)` in the registry validates `(module, got, args)`; for round-trips, any-valid-sample, any-peak.
- `{"ops": [...], "expected": [...]}` — class problems: instantiate `function_name`, replay the method sequence, compare per-op outputs.

### Registries (`judge/registry.py`)

- `@oracle(slug)` — correctness reference (prefer brute force).
- `@judge_case(slug)` — `(n, rng) -> (args, expected[, extras])`. Clamp n into the problem's constraints (the caller sends 0..12); extras carry the same verdict tags as the visible tests.
- `@profiler_input(slug)` — `(n, rng) -> args` of total size ~n that force the worst-case path.
- `@checker(name)` — predicate verdicts.

The random-bracket lesson: a *random* bracket string fails at the first unmatched closer, which would make an O(n) solution measure as O(1). Profiler inputs must be worst-case-shaped — `valid_parentheses` uses n nested opens followed by n closes.

## The profiler

For each of `[100, 200, 400, 800, 1600, 3200, 6400]`, the function runs on worst-case-shaped inputs: 3 repeats per size, median per size, GC disabled around the timed call, `tracemalloc` for peak space, one timed call per subprocess (the subprocess boundary contains hangs — never replace it with in-process timing). A least-squares fit over candidates {O(1), O(n), O(n log n), O(n²), O(n³)} picks the best R², with two safeguards:

- **Occam tiebreak:** when two classes fit within ε of each other, the simpler one wins and confidence is flagged. The O(n) vs O(n log n) case is resolved by log-log slope (≈1.0 vs ≈1.1–1.2 at probe sizes).
- **Honesty contract:** R² < 0.9 → "treat class as suggestive". Exponential growth isn't modeled; superlinear data shows up as a poor fit, not a wrong claim.

Two build-time lessons are baked into the tests: CPython 3.12+ resizes unshared `s[:-1]` strings *in place* (a "quadratic" string rebuild is actually linear), and 4 small sizes with constant overhead can make O(n log n) out-fit O(n) — hence the tiebreak. Don't add heuristics that convert low-confidence fits into confident classes.

## The reviewer

Post-submission, rubric-scored JSON: correctness, approach quality, style/idiom, naming, edge cases, complexity-claim check, **complexity-reasoning** (is the *why* behind the claim sound?), plus **reflection feedback** (prose on the student's reflection — feedback, not a score), broader picture, overall comment. Inputs: statement, submitted code, self-reported complexity (the raw strings, so the reasoning is visible), measured complexity, expected complexity, the static-analysis block, and the student's reflection — which is why reflection now happens *before* the review. Hard rules: it critiques, never repairs — no alternative solutions, no code. Terminal-safe: plain text only, `de_markdown` applied at display time (underscores are never stripped — they may be identifiers like `two_sum`).

Model output is schema-normalized (`reviewer.normalize_review`) before display and storage: rubric dimensions may arrive as `{"score", "comment"}` dicts or as bare numbers, and either shape must render (a real solve once returned bare ints and the chart came out empty).

## Static analysis (v0.4, advisory since v0.6)

Runs at **every `check`** as advisory findings (radon cyclomatic complexity per function + ruff), so the student can fix them before the reviewer ever sees the code — the trainer-not-exam stance: the style score grades the final submitted code, and the live loop itself teaches the habit. Submit still stores the analysis (`static_analysis` JSON) and feeds it to the reviewer as evidence ("reference it where relevant — never invent findings"). Complexity above the McCabe convention (10) is a flag, never a failure; tool hiccups degrade into `notes`.

## The post-solve loop (v0.6)

After review + reflection, the session continues with `polish` (re-judge + re-measure + re-analyze the edited code, updating the same attempt row and bumping its `polished` counter; an optional second review), `discuss <question>` (free post-solve chat — the never-solve boundary lifts after solving; the transcript persists on the attempt row), and `done` (retire the state).

## Per-pattern score trends (v0.4)

`db.review_trends` aggregates the reviewer's rubric per pattern with recency-linear weighting (the oldest of n attempts weighs 1, the newest n). Rendered as the "Score trends per pattern" table in `dojo progress`. Missing or malformed reviews are skipped.
