# Architecture

## Design principles

1. **Never solve, always scaffold.** Enforced in layers: the tutor's context contains only the statement, your code, the ladder tier, and hint history — never reference solutions; hard rules in the system prompt; and a leak-check call that scores every hint 1–5 and regenerates anything ≥ 3.
2. **The tutor and the reviewer are different agents.** One guides during the solve, the other grades after it. A single agent would grade its own hints and "repair" your code.
3. **Empirical complexity is evidence, not proof.** The profiler fits growth curves and reports R², slope, and confidence. A mismatch is a flag to investigate — it may be the algorithm, the claim, or measurement noise. Distinguishing those is itself the lesson.
4. **You state your complexity before the machine measures it.** Interview behavior is the real signal for ML research engineer loops.
5. **The learner model is the asset.** Problems are a commodity; `attempts` rows are the durable record of what actually happened.
6. **Dogfood or die.** Every feature must serve a real session within days of being built — the tool is allowed to exist only to the extent it produces actual solves.

## The never-solve boundary

The never-solve rule is an *architectural* property, not a prompt detail. Reference implementations exist in exactly one place — `judge/registry.py` (oracles, checkers) — and the tutor's imports can never reach them:

- The tutor prompt receives only: statement, student code, tier, hint history.
- The curator agent is structurally separate from the tutor; its outputs land in the judge quarantine zone.
- `tests/test_never_solve.py` pins the boundary mechanically: tutor sources must never reference `dojo.judge`, `dojo.curator`, `dojo.fetcher`, `ORACLES`, or `CHECKERS`, and the built tutor prompt must contain no solution data.

## Component map

```
src/dojo/
  cli.py            # argparse entry: init / list / day / warmup / check / profile /
                    # history / show / progress / curate / fetch
  config.py         # paths, env, backend selection (DEEPSEEK_API_KEY, DOJO_AI_BACKEND)
  editor.py         # $EDITOR launching: detached GUI, tmux/macOS windows for terminal editors
  db.py             # SQLite schema (users, problems, attempts, pattern_cards) +
                    # migrations + attempt-history and trends queries
  bank.py           # seed importer: problems/**/*.py docstrings -> problems
  complexity.py     # O(...) normalization + mismatch logic
  patterns.py       # the pattern taxonomy + LeetCode tag -> pattern mapping
  static.py         # radon cyclomatic complexity + ruff at submit
  scheduler.py      # FSRS-lite cards, due reviews, warm-up + new-problem picks
  judge/            # registry (oracles, generators, checkers) + subprocess runner
  profiler/         # fit (curve fitting) + measure (doubling sizes, tracemalloc)
  tutor/            # backend (mock | deepseek), prompts, hint ladder, reviewer
  curator/          # AI curation pipeline (propose, validate, apply-with-rollback, dual-oracle)
  fetcher/          # LeetCode GraphQL intake: HTML -> text, snippet -> signature
  session/          # workbench state + the day flow (solve & warmup modes)
problems/           # the seed corpus: one problem per file, prompt in the module
                    # docstring, organized by pattern directory
data/problem_overrides.json   # curated metadata: function_name + visible_tests + signatures
```

## Data model

- `users(name)` — one row per person; all data is per-user from day one.
- `problems(slug, title, difficulty, pattern, statement, function_name, expected_time, expected_space, visible_tests, signature)` — the catalog. `function_name` + `visible_tests` + `signature` = "curated", i.e. ready for `dojo day`. `signature` is a def string, `{"functions": {...}}` for multi-function problems, or `{"methods": {...}}` for class problems.
- `attempts(user, problem, kind[solve|warmup], code, status, hint_count, hints JSON, self_reported_*, measured_*_class + r², review JSON, reflection, static_analysis JSON, timings)` — the learner model. One invocation = one attempt row.
- `pattern_cards(user, pattern, stability, difficulty, reps, lapses, due_at, last_review_at, last_reflection, ...)` — the retention schedule; one card per (user, pattern).

`data/dojo.db`, `workbench/`, and `data/dojo.conf` are gitignored: personal state, not source. Migrations are additive only (`ALTER TABLE ... ADD COLUMN` or new tables); user data is never reset as a side effect. `db.connect()` owns the schema — a fresh DB gets the full `SCHEMA` on first connect.

## The daily flow, mechanically

`solve in $EDITOR → check (visible tests + advisory static analysis) → hint ladder → submit → judge (visible + generated + oracle) → self-report complexity → empirical profiler → three-way complexity table → reflection → AI review → post-solve loop (polish / discuss / done) → persist attempt`.

### Tutor modes (v0.6)

One `hint` command, two modes the model classifies: **ladder** (the student is stuck — respond at the current tier and advance, vague messages force tier 0) and **discussion** (the student is exploring — answer directly, no tier, no progression). The never-solve boundary holds in both; every response passes the leak audit, and a response still rated ≥ 3 after retries is discarded, never shown. History entries record the mode.

Session semantics:

- Workbench state is per (slug, kind) and lasts exactly one session: retired (deleted) on submit and on quit, so every `dojo day` invocation gets a fresh attempt row — repeat sessions never overwrite earlier rows, and a warm-up never reuses a solve session's tier/hints.
- Quitting persists code + hints to the abandoned row.
- Every new session writes a blank template over the workbench file; previous solutions live on attempt rows and are recoverable via `dojo history` / `dojo show <id>`.

## Editor launching

All `$EDITOR` behavior lives in `editor.py`. GUI editors detach via `Popen(start_new_session=True)`; terminal editors get a new tmux window inside tmux or a new Terminal/iTerm window on macOS via osascript; unknown editors fall back to blocking with a warning. Override with `DOJO_EDITOR`.

## CLI conventions

- **Entry point (v0.5):** bare `dojo` runs the daily routine (argv normalization: a first non-flag, non-subcommand argument is a slug); `dojo day` is the documented alias. A status line ("N warm-up card(s) due") precedes the session; a footer ("tomorrow: … · best pattern: …") follows it.
- **One computer, one user:** no `--user` flags anywhere. The active user resolves from gitignored `data/dojo.conf` → the DB's sole user; zero users means first run, which triggers the setup wizard (`dojo/setup.py`, pure injectable logic) and then continues the original command. Non-TTY first runs print guidance instead of prompting.
- **Auto-reseed:** every CLI entry (except `setup`) runs `bank.ensure_seeded` — the bank always mirrors `problems/` (idempotent upsert, additive-only, at the CLI layer, not in `db.connect()`).
- **`dojo user [name]`** switches the active user; no name → numbered picker. A conf user missing from the DB is an error, never a silent typo'd account.
- `history` (list attempts, newest first) and `show <id>` (full attempt detail) render rows fetched by `db.list_attempts` / `db.get_attempt`.
- Interactive flows read from `console.input`; tests use the `FakeConsole` fixture (its `actions` hook simulates editing the workbench mid-session).

## Known limitations

- The profiler models polynomial-ish growth only; exponential/constant-factor pathologies show as low-R² reports.
- `generate_parentheses` has no profiler input (its output is exponential, so polynomial fitting would misreport the algorithm); `peak_elements`, `min_stack` and `valid_sudoku` have none either (O(log n) is flat at probe sizes, O(1) per op is flat, and a sudoku board is fixed 9×9).
- The judge compares by strict JSON equality by default (float `1.0` vs `1` mismatch); per-case comparators (`sorted` / `approx` / `rounded` / `predicate` / `ops`) handle any-order outputs, floats, property checks, and class APIs.
- Session duration is measured from session start, not across editor time.
- Terminal editors detach only inside tmux or on macOS; elsewhere `open` falls back to blocking.
- `dojo fetch`'s contract is pinned against canned GraphQL fixtures — the live LeetCode endpoint is unversioned, so a schema drift surfaces as a `LeetCodeError` rather than a silent half-fetch.
