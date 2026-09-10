# AGENTS.md

Guidance for humans and AI agents working on this repository.

## What this is

dojo is an AI-guided interview-prep trainer: a CLI (`dojo`) that runs a daily loop of warm-up retrievals → solve → judge → self-report complexity → empirical profiler → AI review → reflection, persisted to SQLite, with FSRS-lite spaced repetition deciding what comes back when. Its defining constraint is the **never-solve rule**: the tutor agent guides, it never solves. Read `README.md` first (the user-facing pitch + guide); design docs live in `docs/`, delivered and planned stages in `roadmap/`, and everything below assumes that split.

## Layout map

```
src/dojo/
  cli.py            # argparse entry: bare `dojo` = the daily routine; list / day /
                    # warmup / check / profile / history / show / progress /
                    # user / setup / curate / fetch
  setup.py          # the setup wizard: pure injectable logic (key -> .env, user,
                    # PATH wrapper + rc consent); first run triggers it
  config.py         # paths + env (DEEPSEEK_API_KEY, DOJO_AI_BACKEND=mock|deepseek)
  editor.py         # $EDITOR launching: GUI -> detached process; terminal ->
                    # tmux new-window / macOS osascript; unknown -> blocking
  db.py             # schema (users, problems, attempts, pattern_cards) +
                    # migrate() + attempt-history queries; MIGRATIONS MUST BE ADDITIVE
  bank.py           # problems/**/*.py docstring -> problems importer (upsert on slug)
  complexity.py     # O(...) canonicalization; only KNOWN_CLASSES participate in mismatch()
  patterns.py       # pattern taxonomy + LeetCode topic-tag -> pattern mapping (one source of truth)
  static.py         # radon cyclomatic complexity + ruff at submit; evidence, never a verdict
  scheduler.py      # FSRS-lite (stability/difficulty/forgetting curve), due cards,
                    # record_grade, warmup + new-problem picks, backfill
  judge/
    registry.py     # oracles + test generators + profiler inputs + predicate
                    # checkers (per-slug / per-name registries)
    runner.py       # subprocess isolation; JSON protocol; per-case verdict modes
  profiler/
    fit.py          # OLS curve fitting, Occam tiebreak, honesty flags
    measure.py      # one timed call per subprocess, tracemalloc, median-of-repeats
  tutor/
    backend.py      # AIBackend protocol; DeepSeekBackend + MockBackend
    prompts.py      # TUTOR_SYSTEM / LEAK_CHECK_SYSTEM / REVIEWER_SYSTEM + builders
    tutor.py        # hint ladder (tiers 0-5), leak audit, de_markdown terminal cleanup
    reviewer.py     # post-submission rubric review
  curator/
    prompts.py      # CURATOR_SYSTEM (separate agent; never tutor context)
    curator.py      # propose / validate / apply-with-rollback + verification gate
  fetcher/
    htmltext.py     # HTML -> plain text for LeetCode content (stdlib HTMLParser)
    leetcode.py     # GraphQL intake, snippet -> signature, land() into the bank
  session/
    state.py        # workbench/<slug>.state.json (tier, hints, attempt id, kind)
    flow.py         # run_day (solve & warmup modes) + run_warmups
data/problem_overrides.json   # curated metadata: function_name + visible_tests + signatures
problems/           # seed corpus: one problem per file, prompt in module docstring,
                    # grouped by pattern (arrays_and_hashing, stack, two_pointers,
                    # trees, heap, binary_search, greedy, dynamic_programming, math,
                    # linked_list, graph, backtracking, sliding_window, bit_manipulation)
tests/              # offline; mock backend
workbench/          # gitignored scratch; attempt code persists in the DB, not here
Makefile            # sync/test/demo targets with a workspace-local UV_CACHE_DIR
docs/               # technical docs: architecture, grading, retention, curation, development
roadmap/            # delivered stages (v0.1..v0.4) and next.md (planned)
```

## Setup and commands

```bash
make sync                  # uv sync with UV_CACHE_DIR=.uv-cache (sandbox-safe)
make test                  # uv run pytest -q
make seed                  # scripted first-run: dojo setup --user andy --skip-key --no-path
uv run dojo                # bare entry = the daily routine; first run opens the setup wizard
DOJO_AI_BACKEND=mock uv run dojo   # offline demo of the full pipeline
uv run dojo warmup         # due retrievals only
uv run dojo progress       # per-pattern proficiency + cards + score trends
```

Python ≥ 3.13. Deps are managed by uv; add new ones with `uv add`, never by hand-editing the lockfile. **Always route uv through `make` targets or set `UV_CACHE_DIR=$(pwd)/.uv-cache` yourself** — the default uv cache lives outside the workspace and trips sandbox file policies.

## Hard rules

1. **Never-solve is an architectural property, not a prompt detail.** Reference implementations (oracles in `judge/registry.py`) must never enter tutor context. The tutor prompt (`tutor/prompts.py`) receives only: statement, student code, tier, hint history. If a change adds a new file with solution code, keep it outside anything the tutor imports or reads.
2. **Copyright — private use.** dojo serves two PhD students' private practice. Statements, visible tests, and other data may draw on public sources (LeetCode, books) and live in the bank as normal; the repo stays private — never publish the bank or its data. The seed corpus is the users' own writing where it exists.
3. **Secrets.** `DEEPSEEK_API_KEY` lives in the environment or a gitignored `.env`. Never log it, never put it in prompts, tests, or fixtures.
4. **User data is real.** `data/dojo.db` and `workbench/` are personal state. Don't delete or reset them as a side effect; DB migrations are additive only (`ALTER TABLE ... ADD COLUMN` or new tables).
5. **Tests are offline and deterministic.** No network calls in tests; always use `MockBackend`. Measurement tests target coarse outcomes (class, slope range), not exact timings.
6. **Prompt changes require test updates.** The leak-check behavior, tier gating, and mock canned responses are asserted in `tests/test_tutor.py` and `tests/test_flow.py`. Change a prompt → update the mock to mirror it and adjust the assertions in the same commit.
7. **Respect the honesty contract.** The profiler reports evidence ("consistent with O(n) at tested scales", R², confidence), never proofs. Don't add heuristics that convert low-confidence fits into confident classes.

## Conventions

- **Judge protocol:** `runner.py` writes `solution.py` + `cases.json` + a harness into a temp dir and executes it with a timeout. Case dicts: `{"args": [...], "expected": any, "label": str}` plus optional verdict tags — `"compare": "sorted"` (deep-sorted equality for any-order outputs), `"compare": "approx:1e-4"` / `"rounded:n"` (float tolerance), `"predicate": name` (a `@checker` in the registry validates `(module, got, args)`), or `{"ops": [...], "expected": [...]}` (class problems: instantiate `function_name`, replay the method sequence). Default is strict JSON equality with `sort_keys` — don't "fix" it to approximate float equality without updating README and tests.
- **Registries:** per-slug decorators in `judge/registry.py`: `@oracle(slug)` (correctness reference), `@judge_case(slug)` (small random cases with expected values; may return a third extras dict carrying the same verdict tags), `@profiler_input(slug)` (worst-case-shaped inputs of size n — never early-exit inputs; see the random-bracket lesson in docs/grading.md), and `@checker(name)` (predicate verdicts). Generators must clamp n into the problem's constraints (the caller sends 0..12).
- **Measurement protocol:** one timed call per subprocess; GC disabled around the call; tracemalloc started after module import; median across repeats. The subprocess boundary exists to contain hangs — don't replace it with in-process timing.
- **Curating a new problem:** add `function_name` + `visible_tests` + a `signature` (string for one function, `{"functions": {...}}` for multi-function problems, `{"methods": {...}}` for class problems) to `data/problem_overrides.json`, and a generator/oracle pair in `judge/registry.py` (a `@checker` for predicate problems, a `@profiler_input` unless measurement is meaningless). The startup auto-reseed keeps the DB fresh (an upsert, so it never deletes rows attempts reference). The judge's verdict modes mean prompts can honestly say "any order": tag those cases `"compare": "sorted"` and emit canonical form from the oracle. Trees are nested lists `[value, left, right]` (`None` = missing child / empty tree). `tests/test_registry.py` pins the contract — update it when the curated set changes. `dojo curate` automates the recipe via the curator agent (a separate agent from the tutor — its oracle output must never enter tutor context; `tests/test_never_solve.py` pins that boundary) and applies only when the verification gate passes, rolling back otherwise.
- **Static analysis (v0.4):** runs automatically on every successful submit (`static.analyze`): radon cyclomatic complexity per function + ruff findings, stored on the attempt row (`static_analysis` JSON) and fed to the reviewer prompt as evidence. Complexity > 10 (McCabe convention) is a flag, never a failure; tool hiccups degrade into `notes`. Add new deps with `uv add` — never hand-edit the lockfile.
- **Fetcher (v0.3):** `dojo fetch <title-slug>` pulls a LeetCode problem (GraphQL), converts content HTML to plain text (`fetcher/htmltext.py`, stdlib only), maps topic tags → pattern via `patterns.py` (unmapped tags fail loudly — never a silent wrong bucket), parses the python3 starter snippet into `function_name` + `signature` hints (annotation normalization: `List[int]` → `list[int]`, `Optional[X]` → `X | None`; empty snippet bodies get padded), lands the seed file via `fetcher.land()`, then auto-curates through the curator + verification gate. The HTTP transport is an injected callable — tests pin the contract against canned GraphQL fixtures and must never hit the network.
- **Tutor protocol (v0.6):** one `hint` command, two AI-classified modes — "ladder" (stuck: respond at the tier, advance; only ultra-short zero-information messages force tier 0) and "discussion" (exploring: answer directly, no tier). `ask_tutor` calls `chat_json` with a `{"kind", "tier", "text"}` schema; every response passes the leak audit, and one still rated >= 3 after retries is **discarded, never shown**. History entries record `kind`. The post-solve `discuss` command uses `DISCUSSION_SYSTEM` (boundary lifts after solving) and persists the transcript. The reviewer returns a normalized rubric (bare-int dimensions wrapped by `reviewer.normalize_review`), including `complexity_reasoning` + `reflection_feedback` — change any prompt → update the mock and tests in the same commit (rule 6).
- **Report command (v0.7):** `dojo report [slug]` (and in-session `report`) audits curation via `curator.audit_curation`: fresh curator run → cross-check fresh oracle vs live oracle on generated cases → audit agent hunts prompt-vs-judge contract violations. `--fix` re-curates (`apply(overwrite=True)` — new registry block wins at import; rollback restores original files, overrides, registrations). Report JSON lands in gitignored `data/curation/`.
- **Terminal ergonomics:** interactive prompts use `dojo/terminal.make_prompt` (prompt_toolkit when on a TTY — arrow keys, wrapped-line editing, history; `console.input` otherwise, which tests exercise). Rich tables come from `dojo/ui.table` (vertical padding between rows). Tutor/discussion responses cap at 2048 tokens; `de_markdown` handles bullets, headers, blockquotes, horizontal rules, and dunder bolds — keep it updated as models invent new artifacts.
- **Scheduler:** the FSRS-lite model lives entirely in `scheduler.py` with documented constants (FACTOR/DECAY/S0/D0/TARGET_R). Grades are 1-4 (Anki convention). Don't swap in a scheduler library without porting `tests/test_scheduler.py`; same-day reviews legitimately yield no stability growth (R ≈ 1).
- **Warm-up semantics:** `run_warmups` forces a fresh template (re-solve from scratch), creates an attempt with `kind='warmup'`, skips reflection (the recall grade replaces it), and quits record a lapse. Workbench state is per (slug, kind) and lasts exactly one session: it is retired (deleted) on submit and on quit, so every `dojo day` invocation gets a fresh attempt row — a warm-up never reuses a solve session's tier/hints, and repeat sessions never overwrite earlier attempt rows. Quitting persists code + hints to the abandoned attempt row. **Every new session writes a blank template over the workbench file** (solves and warm-ups alike); previous solutions live on attempt rows and are recoverable via `dojo history` / `dojo show <id>`.
- **Terminal-safe AI output:** tutor and reviewer prompts instruct plain text (no Markdown); `de_markdown` in `tutor/tutor.py` is the belt-and-braces cleanup applied at display time. Underscores are never stripped (they may be identifiers like `two_sum`); pin this with tests in `tests/test_tutor.py`.
- **Editor launching:** all `$EDITOR` behavior lives in `editor.py` — GUI editors detach via `Popen(start_new_session=True)`, terminal editors go through tmux/osascript, unknown editors block. Don't call subprocess directly from `flow.py`; tests cover the pure classification helpers only, never process spawning.
- **SQLite:** `db.py` owns schema and connection. Keep `sqlite3.Row` access by name. JSON columns go through `dumps_json`/`loads_json`.
- **CLI:** argparse subcommands in `cli.py`; each returns an exit code. Bare `dojo` runs the daily routine (argv normalization: a first non-flag, non-subcommand argument is a slug; `dojo day` is the alias). **One computer, one user** — no `--user` flags: the active user resolves from gitignored `data/dojo.conf` → the DB's sole user; zero users = first run → the setup wizard (`dojo/setup.py`) runs, then the original command continues (non-TTY prints guidance instead of prompting). Every entry (except `setup`) runs `bank.ensure_seeded` first — the bank always mirrors `problems/` (additive upsert; at the CLI layer, never in `db.connect()`). `dojo user [name]` switches the active user (numbered picker without a name; an unknown name errors — never a silent typo'd account). Interactive flows read from `console.input` — tests use the `FakeConsole` fixture (its `actions` hook simulates editing the workbench mid-session). `history` (list attempts, newest first) and `show <id>` (full attempt detail, `--code` for code only) render rows fetched by `db.list_attempts` / `db.get_attempt`.

## Definition of done

- `uv run pytest` passes; new behavior has tests.
- The never-solve boundary is unchanged or deliberately narrowed with rationale in the PR description.
- User-visible changes update `README.md` (guide) and the matching `docs/` file (technical); new stage work lands in `roadmap/`.
