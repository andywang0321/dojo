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

**The one deliberate narrowing (v0.8):** learning mode's teacher may show *topic-canonical* code, because its context contains no pending problem — only the topic name and the conversation. Never-solve protects solves, not knowledge. The narrowing is documented here, pinned by a guard test (`test_teacher_prompt_carries_topic_only`), and does not extend: grading oracles still never enter tutor, teacher, or reviewer context.

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
  roadmap.py        # parses data/roadmap.toml (18 groups x ordered ladders) into
                    # the structures the scheduler + the roadmap view consume
data/roadmap.toml   # vendored NeetCode 150 structure (provenance header)
problems/           # the seed corpus: one problem per file, prompt in the module
                    # docstring, organized by pattern directory
data/problem_overrides.json   # curated metadata: function_name + visible_tests + signatures
```

## Data model

- `users(name)` — one row per person; all data is per-user from day one.
- `problems(slug, title, difficulty, pattern, statement, function_name, expected_time, expected_space, visible_tests, signature, lc_number)` — the catalog. `function_name` + `visible_tests` + `signature` = "curated", i.e. ready for `dojo day`. `signature` is a def string, `{"functions": {...}}` for multi-function problems, or `{"methods": {...}}` for class problems. `lc_number` (v0.10) ties a problem to its LeetCode number — the roadmap ladder matches on it; problems without one (dojo's own) sit outside the ladder.
- `attempts(user, problem, kind[solve|warmup], code, status, hint_count, hints JSON, self_reported_*, measured_*_class + r², review JSON, reflection, static_analysis JSON, timings, recall_grade)` — the learner model. **A row exists iff the student submitted** (v0.11): it is created on the first submit of a session, pass or fail, and updated thereafter, so `status` carries the judge's own verdict instead of a placeholder. `quit` records nothing. `recall_grade` (1–4) holds the warm-up grade — the retention model's one input, which used to be folded into the card aggregates and discarded.
- `pattern_cards(user, pattern, stability, difficulty, reps, lapses, due_at, last_review_at, last_reflection, ...)` — the retention schedule; one card per (user, pattern), updated by the published FSRS-4.5 equations with default weights (see docs/retention.md).
- `learn_sessions(user, pattern, transcript JSON, created_at, completed)` — one row per learning-mode session (v0.8); the transcript is rewritten after each exchange, `completed` flips to 1 on graceful exit.

`data/dojo.db`, `workbench/`, and `data/dojo.conf` are gitignored: personal state, not source. Migrations are additive only (`ALTER TABLE ... ADD COLUMN` or new tables); user data is never reset as a side effect. `db.connect()` owns the schema — a fresh DB gets the full `SCHEMA` on first connect.

## The daily flow, mechanically

`solve in $EDITOR → check (visible tests + advisory static analysis) → hint ladder → submit → judge (visible + generated + oracle) → self-report complexity → empirical profiler → three-way complexity table → reflection → AI review → post-solve loop (polish / discuss / done) → persist attempt`.

### Tutor modes (v0.6)

One `hint` command, two modes the model classifies: **ladder** (the student is stuck — respond at the current tier and advance, vague messages force tier 0) and **discussion** (the student is exploring — answer directly, no tier, no progression). The never-solve boundary holds in both; every response passes the leak audit, and a response still rated ≥ 3 after retries is discarded, never shown. History entries record the mode.

### Learning mode (v0.8)

A third agent, the **teacher**, for topic education — the mode error "what is a heap" exposed (the hint ladder unblocks problems; it doesn't teach topics). Three entry points share one `run_learn`:

- **`dojo learn [topic]`** — picker without a topic, did-you-mean on typos. Primer, then a free conversation where every bare line is a message. `practice` hands off to the easiest unsolved curated problem in the pattern.
- **In-session `learn`** — parks the current attempt (quit persistence: code + hints saved, status stays 'unsolved', state retired) and teaches the current pattern (or a named topic). Accepting the handoff returns the outcome `"practice"` with the *same* slug; `_cmd_day` loops into a fresh blank-template session. Declining and `done` end the day — grading honesty is preserved because a post-study solve is a fresh attempt.
- **The proactive offer** — when the scheduler picks a problem from an unstudied pattern (no learn session, no attempts) and no explicit slug was given: "learn first? [y/N]". One keystroke declines; it is a fork, never a gate.

The transcript persists to `learn_sessions` after every exchange (a crash loses at most one turn); `completed` marks graceful ends. `studied_patterns` (any learn session **or** any attempt) is the single notion feeding both the offer and the `dojo progress` markers. Warm-up sessions reject `learn`: a warm-up is a graded recall, and leaving one is a lapse, not a pause.

The teacher's guard rails: `TEACHER_SYSTEM` avoids the words "tutor" and "discussion" (MockBackend keys its canned branches on system-prompt substrings — pinned by test), shows plain text only, and is instructed to say so when unsure — there is no oracle for pedagogy.

### The progression (v0.10)

The pattern set is NeetCode's 18 technique groups in the roadmap's order (`patterns.PATTERNS`), and `data/roadmap.toml` (vendored from the public NeetCode 150 mirror, provenance-credited) defines each group's ordered problem ladder by LeetCode number. `patterns.PREREQS` encodes dojo's reading of the progression — a chain over the verified group order (the mirrored data carries the order, not the site's explicit DAG edges; one-line adjustment if a different edge set is wanted).

The daily pick walks the groups top-down under a **hard prereq gate**: a pattern is eligible only when every prerequisite has no unsolved ladder problem left in the bank; the pick is the earliest unsolved ladder problem of the first eligible pattern. Uncurated rows are invisible to the ladder (it never serves what it can't grade). Once the ladder in the bank is complete, dojo's own problems are the fallback (weakest pattern first, the v0.1 behavior). Explicit `dojo <slug>` bypasses the gate — deliberate choices are exempt, matching the proactive-offer precedent. `dojo roadmap` renders the tree (✓ complete · → next up · locked — finish X); the learn-mode practice handoff (`pick_practice_problem`) respects ladder order within its pattern.

Session semantics:

- Workbench state is per slug (carrying its kind) and lasts exactly one session: retired on submit and on quit, so every `dojo day` invocation starts fresh — repeat sessions never overwrite earlier rows, and a warm-up never reuses a solve session's tier/hints.
- Quitting records nothing at all — no row, no hints, no lapse (v0.11). The state file is retired, so a quit is a total abandonment.
- Every new session writes a blank template over the workbench file; submitted code lives on attempt rows and is recoverable via `dojo history` / `dojo show <id>`.
- **Crash recovery is the only resume path**: a session killed before submitting leaves its state file behind, and the next invocation resumes it with its code and hints intact.

## Editor launching

All `$EDITOR` behavior lives in `editor.py`. GUI editors detach via `Popen(start_new_session=True)`; terminal editors get a new tmux window inside tmux or a new Terminal/iTerm window on macOS via osascript; unknown editors fall back to blocking with a warning. Override with `DOJO_EDITOR`.

## CLI conventions

- **Entry point (v0.5):** bare `dojo` runs the daily routine (argv normalization: a first non-flag, non-subcommand argument is a slug); `dojo day` is the documented alias. A status line ("N warm-up card(s) due") precedes the session; a footer ("tomorrow: … · best pattern: …") follows it.
- **Minimal help (v0.9):** `dojo help` = `dojo -h` = `dojo --help`, intercepted in `main` before argparse, prints a hand-written guide: bare `dojo` usage plus seven everyday commands (`learn`, `list`, `progress`, `history`, `fetch`, `user`, `setup`). Power tools (`day`, `warmup`, `check`, `show`, `curate`, `report`, and `profile` — a hidden alias of `history`) stay dispatchable and self-document via `dojo <cmd> --help`, but never appear in the guide. Note: argparse's `help=SUPPRESS` prints `==SUPPRESS==` literals on Python 3.13, so the hiding lives in the interception, not the parser.
- **Setup wizard key detection (v0.9):** `run_wizard` resolves the key as environment → dotenv → prompt. A detected key skips the prompt; an env-sourced key is persisted to the dotenv so every shell sees it. `--skip-key` disables detection too (scripted installs like `make seed` never write a key), and when the PATH install is declined the closing line points at `uv run dojo`.
- **The practice loop (v0.8):** `_cmd_day` and `_cmd_learn` run solve sessions through `_run_practice_session`, which loops while the outcome is `"practice"` (the in-session learn handoff) — always the same slug. `run_warmups` treats `"practice"` like quit.
- **Learning mode (v0.8):** `dojo learn [TOPIC]` (USER_COMMANDS member — needs the active user); no topic → the shared `_choose` numbered picker (generalized from the user picker); unknown topic → a `difflib` did-you-mean, never a silent wrong pattern.
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
- The teacher has no grader or oracle behind it; the humble-teacher instruction is a mitigation, not a verification. Learning-mode transcripts are stored but not resumable in v0.8.
