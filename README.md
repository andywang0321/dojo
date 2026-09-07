# dojo

An AI-guided interview-prep trainer for two PhDs (data science, bioengineering) who write production Python and know ML deeply, but never had a formal CS algorithms course. dojo is built on one conviction: **the tutor never solves the problem for you — it teaches you to recognize the pattern behind it.**

Three components:

1. **A never-solve tutor** (DeepSeek) — a gated hint ladder that unblocks thinking without leaking solutions, with a second model call auditing every hint for spoilers.
2. **A grading engine** — quantitative: an isolated judge (visible, generated, and oracle-checked tests) plus an empirical profiler that *measures* time/space growth; qualitative: a rubric-based AI review of approach, style, and edge-case habits.
3. **A retention engine** — FSRS-lite spaced repetition over pattern cards: `dojo day` starts with warm-up retrievals (re-solving past problems from scratch), grades your recall, and schedules the next review. A problem bank + learner model underpin all three: problems are a catalog; the asset is your attempt history and card schedule.

## Design principles

1. **Never solve, always scaffold.** Enforced in layers: the tutor's context contains only the statement, your code, the ladder tier, and hint history — never reference solutions; hard rules in the system prompt; and a leak-check call that scores every hint 1–5 and regenerates anything ≥ 3.
2. **The tutor and the reviewer are different agents.** One guides during the solve, the other grades after it. A single agent would grade its own hints and "repair" your code.
3. **Empirical complexity is evidence, not proof.** The profiler fits growth curves and reports R², slope, and confidence. A mismatch between expected / claimed / measured classes is a flag to investigate — it may be the algorithm, the claim, or measurement noise. Distinguishing those is itself the lesson.
4. **You state your complexity before the machine measures it.** Interview behavior is the real signal for ML research engineer loops.
5. **The learner model is the asset.** Problems are a commodity; `attempts` rows are the durable record of what actually happened.
6. **Dogfood or die.** Every feature must serve a real session within days of being built — the tool is allowed to exist only to the extent it produces actual solves.

## The daily loop

```
dojo day
```

0. **Warm-up** (if any cards are due) — the scheduler re-opens a previously solved problem in the due pattern, *from scratch*: fresh template, same full pipeline. After submitting you grade your own recall (4 = easy, 3 = good, 2 = hard, 1 = forgot) and the card's next review is scheduled.
1. **Read** the problem (printed in the terminal). Nothing opens automatically; `dojo day` picks for you — weakest pattern first, then lowest difficulty.
2. **Open** — `open` launches `$EDITOR` without blocking the prompt: GUI editors (zed, code, …) get a detached process; terminal editors (nvim, vim, …) get a new tmux window inside tmux, or a new Terminal/iTerm window on macOS. Use `dojo day --open` to auto-open on launch.
3. **Check** — run visible tests as often as you like (`check`). The editor stays open; the prompt stays live.
4. **Hint** — when stuck, `hint <what you're stuck on>`. Hints are metered and logged.
5. **Submit** — the judge runs visible + generated + oracle-checked cases in a subprocess.
6. **Self-report** — state your time/space complexity and *why* (typed, before any measurement).
7. **Measure** — the profiler runs your code on doubling input sizes and classifies growth.
8. **Compare** — a three-way table: expected vs. claimed vs. measured, with mismatch flags.
9. **Review** — the AI reviewer scores a rubric (correctness, approach, idiom, naming, edge cases, complexity claim) and writes a "broader picture" note connecting the problem to its pattern family and your ML background.
10. **Reflect** — one prompt feeds the pattern card: what was the key insight, and when would you reach for this again?

Everything lands on an `attempts` row in SQLite (kind = `solve` or `warmup`); new solves create/refresh the pattern's card. The command list (`check · hint <text> · open · submit · quit`) is reprinted after every output, so it's always at the bottom of your screen. `dojo warmup` runs due retrievals on their own; `dojo progress` shows per-pattern proficiency and the card schedule.

## The retention engine (v0.2)

FSRS-lite: each (user, pattern) card carries two numbers — **stability S** (memory strength, days) and **difficulty D** (1–10) — plus a due date. Recall probability follows the FSRS forgetting curve `R(t) = (1 + 19/81 · t/S)^(−0.5)`, so `R ≈ 0.90` at `t = S`; the next review is scheduled when retrievability decays to 0.9 (which, with these constants, is simply `interval = S`). Successful recalls grow stability (more for easy, less for hard cards, damped as S grows) and ease difficulty; lapses roughly halve stability and raise difficulty. Grading follows Anki's convention (1–4), and the suggested grade is derived from hints used: 0 hints → 4, 1 → 3, 2+ → 2. Quitting a warm-up records a lapse. Reviewed-too-early (R ≈ 1) deliberately yields no growth — that's the model, not a bug.

The scheduler also decides **what to solve next**: curated problems you haven't solved, ordered by weakest pattern (lowest average card stability; untouched patterns count as 0) then difficulty. And warm-ups re-solve the *least recently solved* problem in the pattern — oldest memory, most worth retrieving. Cards from v0.1 history are backfilled by `dojo init` (due immediately).

## The hint ladder

Each `hint` call advances one rung (capped at 5). A vague message ("stuck") forces rung 0 first — articulating the blockage is metacognition before assistance.

| Tier | Name | What it may do |
|------|------|----------------|
| 0 | Articulate the blockage | Ask what you've tried and where exactly you're stuck |
| 1 | Conceptual nudge | Point at a property or invariant, no names |
| 2 | Pattern recognition | Name the problem family |
| 3 | Data structure / invariant | Name the tool and the invariant it maintains |
| 4 | Edge cases | Point at input shapes the code must survive |
| 5 | Skeleton (no code) | Outline the steps in words |

Full discussions and reference solutions unlock only after submission — and v0 keeps reference implementations entirely out of the repo except for judge oracles, which the tutor never sees.

Tutor output is terminal-safe: the prompts instruct plain text (no Markdown), and `de_markdown` strips any asterisks, backticks, headers, and bullets that slip through before display.

## The problem bank and curation

Every problem has a **slug** (a stable machine identifier: the filename stem, e.g. `valid_parentheses`), a **title** (the human-readable name, e.g. "Valid Parentheses"), and a statement. The CLI shows them merged as `Title (slug)` — the slug is what you type, the title is what you read.

Seeding is automatic: `dojo init` imports every `problems/**/*.py` file whose module docstring starts with `Title [Difficulty]` (pattern = parent directory, expected complexity parsed from the "You should aim for..." line).

**Curated** is a stricter bar, and it is a manual, deliberate step — the ✓ column in `dojo list`. A problem is curated when it has everything `dojo day` needs:

1. `function_name` + `visible_tests` in `data/problem_overrides.json` (the interface contract: how the judge calls your code, and the examples you can check against);
2. a signature in `SIGNATURES` (`session/flow.py`) so the workbench template writes the right stub;
3. ideally: a `@judge_case` generator + `@oracle` in `judge/registry.py` (randomized + oracle-checked cases) and a `@profiler_input` (worst-case-shaped inputs for measurement) — without these, submission still works on visible tests only, and the profiler is skipped.

There is no `dojo curate` command: curation can't be automated honestly, because the function signature, test cases, and brute-force oracle are problem-specific knowledge that only a human (or a future LeetCode fetcher for the statement part) can provide. The recipe above is the whole process — pick a slug, write the four entries, re-run `dojo init`, and the ✓ appears. (`two_sum` is a minimal working example: it has 1 and 2, and intentionally no generator/oracle — which is why solving it skips the profiler.)

## The grading engine

**Judge.** Student code runs in an isolated subprocess with a JSON protocol: import the workbench file, call the problem's function, compare results by JSON equality, kill on timeout. Cases come from three layers: visible examples (curated in `data/problem_overrides.json`), randomized generated cases, and oracle-checked cases where a brute-force reference exists (`dojo/judge/registry.py`). Oracle code is correctness infrastructure only — never tutor context.

**Profiler.** For each of `[100, 200, 400, 800, 1600, 3200, 6400]`, your function runs on worst-case-shaped inputs (never inputs that let it early-exit — a random bracket string fails at the first unmatched closer and would make an O(n) solution *measure* as O(1)), 3 repeats per size, median per size, GC disabled around the timed call, `tracemalloc` for peak space. A least-squares fit over candidates {O(1), O(n), O(n log n), O(n²), O(n³)} picks the best R², with two safeguards:

- **Occam tiebreak:** when two classes fit within ε of each other, the simpler one wins and confidence is flagged — claiming O(n) on ambiguous evidence is the conservative read. The O(n) vs O(n log n) case is resolved by log-log slope (≈1.0 vs ≈1.1–1.2 at our probe sizes).
- **Honesty contract:** R² < 0.9 → "treat class as suggestive". Exponential growth isn't modeled in v0; superlinear data shows up as a poor fit, not a wrong claim.

Two build-time lessons are baked into the tests: CPython 3.12+ resizes unshared `s[:-1]` strings *in place* (a "quadratic" string rebuild is actually linear), and 4 small sizes with constant overhead can make O(n log n) out-fit O(n) — hence the tiebreak.

**Reviewer.** Post-submission, rubric-scored JSON: correctness, approach quality, style/idiom, naming, edge cases, complexity-claim check, broader picture, overall comment. Hard rule: it critiques, never repairs — no alternative solutions in reviews.

## Layout

```
src/dojo/
  cli.py            # init / list / day / warmup / check / profile / progress
  config.py         # paths, env, backend selection (DEEPSEEK_API_KEY, DOJO_AI_BACKEND)
  editor.py         # $EDITOR launching: detached GUI, tmux/macOS windows for terminal editors
  db.py             # SQLite schema (users, problems, attempts, pattern_cards) + migrations
  bank.py           # seed importer: problems/**/*.py docstrings -> problems
  complexity.py     # O(...) normalization + mismatch logic
  scheduler.py      # FSRS-lite cards, due reviews, warm-up + new-problem picks
  judge/            # registry (oracles, generators) + subprocess runner
  profiler/         # fit (curve fitting) + measure (doubling sizes, tracemalloc)
  tutor/            # backend (mock | deepseek), prompts, hint ladder, reviewer
  session/          # workbench state + the day flow (solve & warmup modes)
problems/           # the seed corpus: one problem per file, prompt in the module
                    # docstring, organized by pattern (arrays_and_hashing, stack,
                    # two_pointers, interview/...) — your original solving files
data/problem_overrides.json   # curated metadata: function names + visible tests
tests/                        # 45 tests, no network, mock backend
workbench/                    # scratch space (gitignored); attempt code lives in the DB
Makefile                      # sandbox-friendly entry points (workspace-local uv cache)
```

## Getting started

```bash
make sync                        # or: uv sync  (see the uv-cache note below)
export DEEPSEEK_API_KEY=...      # or put it in a gitignored .env
uv run dojo init --user andy     # create DB, seed the bank from problems/
uv run dojo list --user andy     # catalog with solved status
uv run dojo day --user andy      # warm-ups (if due) + scheduler-picked problem
```

**The uv cache note.** uv writes its package cache to `~/.cache/uv` by default, which is outside this repo. If you run inside a sandbox (CI, an agent harness, a container), use `make sync` / `make test` — the Makefile sets `UV_CACHE_DIR=.uv-cache`, keeping everything inside the workspace so no permission escalation is ever needed.

No API key? `DOJO_AI_BACKEND=mock` runs the whole pipeline with canned responses — everything except real AI text works. `dojo check` and `dojo hint` also work standalone against the active workbench.

## Data model

- `users(name)` — one row per person; all data is per-user from day one.
- `problems(slug, title, difficulty, pattern, statement, function_name, expected_time, expected_space, visible_tests)` — the catalog. `function_name` + `visible_tests` = "curated", i.e. ready for `dojo day`.
- `attempts(user, problem, kind[solve|warmup], code, status, hint_count, hints JSON, self_reported_*, measured_*_class + r², review JSON, reflection, timings)` — the learner model.
- `pattern_cards(user, pattern, stability, difficulty, reps, lapses, due_at, last_reflection, ...)` — the retention schedule; one card per (user, pattern).

`data/dojo.db` and `workbench/` are gitignored: they're personal state, not source.

## Testing

```bash
uv run pytest
```

45 tests cover complexity normalization, curve fitting (including the ambiguity tiebreak), bank parsing/import, judge correctness/crash/timeout, hint-ladder tiering and leak regeneration, Markdown stripping, editor classification, the `open` command, real measurement of linear vs. quadratic code, the FSRS-lite model and card lifecycle, warm-up flows (grade + lapse), and full mocked day flows. Tests never touch the network and use `DOJO_AI_BACKEND=mock` semantics.

## Roadmap

- **v0.3 — the updating bank:** LeetCode GraphQL fetcher with a private, gitignored local cache. Copyright stance: LeetCode problem text and test data are proprietary — fetch on demand for personal use, never commit a scraped corpus to the repo. Curate more problems (signatures move into `problem_overrides.json`).
- **v0.4 — deeper grading:** static analysis (radon cyclomatic complexity, ruff), the hinted-solution penalty, review score trends per pattern.
- **Later:** TUI polish (Textual), two-machine sync, warm-up problem variants. A web UI only if the CLI loop proves insufficient — never first.

## Known limitations (v0)

- One fully curated solve path (`valid_parentheses`); `two_sum` is seeded as a fixture. Every other problem waits for curation (function name + visible tests).
- A warm-up card needs at least one *solved* problem in its pattern to re-solve; cards without one are deferred a day.
- Same-day reviews yield no stability growth (R ≈ 1 at t ≈ 0) — schedule your warm-ups a day or more after solving, which is exactly what the due dates do.
- Terminal editors detach only inside tmux or on macOS (Terminal/iTerm via osascript); elsewhere `open` falls back to blocking with a warning. Unrecognized editors are treated as blocking — add them to `GUI_EDITORS` in `src/dojo/editor.py` if they can detach.
- The profiler models polynomial-ish growth only; exponential/constant-factor pathologies show as low-R² reports.
- The judge compares by strict JSON equality (float `1.0` vs `1` mismatch); oracle-generated cases exist only where a brute-force reference is registered.
- Session duration is measured from session start, not across editor time, and one attempt row = one session.
