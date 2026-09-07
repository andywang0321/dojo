# AGENTS.md

Guidance for humans and AI agents working on this repository.

## What this is

dojo is an AI-guided interview-prep trainer: a CLI (`dojo`) that runs a daily loop of solve → judge → self-report complexity → empirical profiler → AI review → reflection, persisted to SQLite. Its defining constraint is the **never-solve rule**: the tutor agent guides, it never solves. Read `README.md` first; everything below assumes it.

## Layout map

```
src/dojo/
  cli.py            # argparse entry: init / list / day / check / profile
  config.py         # paths + env (DEEPSEEK_API_KEY, DOJO_AI_BACKEND=mock|deepseek)
  editor.py         # $EDITOR launching: GUI -> detached process; terminal ->
                    # tmux new-window / macOS osascript; unknown -> blocking
  db.py             # schema (users, problems, attempts) — MIGRATIONS MUST BE ADDITIVE
  bank.py           # dsa/**/*.py docstring -> problems importer
  complexity.py     # O(...) canonicalization; only KNOWN_CLASSES participate in mismatch()
  judge/
    registry.py     # oracles + test generators + profiler inputs (per-slug registries)
    runner.py       # subprocess isolation; JSON protocol; strict JSON-equality compare
  profiler/
    fit.py          # OLS curve fitting, Occam tiebreak, honesty flags
    measure.py      # one timed call per subprocess, tracemalloc, median-of-repeats
  tutor/
    backend.py      # AIBackend protocol; DeepSeekBackend + MockBackend
    prompts.py      # TUTOR_SYSTEM / LEAK_CHECK_SYSTEM / REVIEWER_SYSTEM + builders
    tutor.py        # hint ladder (tiers 0-5), leak audit, de_markdown terminal cleanup
    reviewer.py     # post-submission rubric review
  session/
    state.py        # workbench/<slug>.state.json (tier, hints, attempt id)
    flow.py         # run_day: the whole session orchestration
data/problem_overrides.json   # curated metadata: function_name + visible tests
dsa/                # seed corpus: one problem per file, prompt in module docstring
tests/              # 33 tests; offline; mock backend
workbench/          # gitignored scratch; attempt code persists in the DB, not here
Makefile            # sync/test/demo targets with a workspace-local UV_CACHE_DIR
```

## Setup and commands

```bash
make sync                  # uv sync with UV_CACHE_DIR=.uv-cache (sandbox-safe)
make test                  # uv run pytest -q
uv run dojo init --user X  # create DB + seed bank (idempotent: INSERT OR REPLACE)
DOJO_AI_BACKEND=mock uv run dojo day <slug> --user X   # offline demo
```

Python ≥ 3.13. Deps are managed by uv; add new ones with `uv add`, never by hand-editing the lockfile. **Always route uv through `make` targets or set `UV_CACHE_DIR=$(pwd)/.uv-cache` yourself** — the default uv cache lives outside the workspace and trips sandbox file policies.

## Hard rules

1. **Never-solve is an architectural property, not a prompt detail.** Reference implementations (oracles in `judge/registry.py`) must never enter tutor context. The tutor prompt (`tutor/prompts.py`) receives only: statement, student code, tier, hint history. If a change adds a new file with solution code, keep it outside anything the tutor imports or reads.
2. **Copyright.** Never commit scraped LeetCode problem statements, editorials, or test data. Fetched content (the v0.3 fetcher) lives in a gitignored local cache only. The seed corpus in `dsa/` is the users' own writing.
3. **Secrets.** `DEEPSEEK_API_KEY` lives in the environment or a gitignored `.env`. Never log it, never put it in prompts, tests, or fixtures.
4. **User data is real.** `data/dojo.db` and `workbench/` are personal state. Don't delete or reset them as a side effect; DB migrations are additive only (`ALTER TABLE ... ADD COLUMN` or new tables).
5. **Tests are offline and deterministic.** No network calls in tests; always use `MockBackend`. Measurement tests target coarse outcomes (class, slope range), not exact timings.
6. **Prompt changes require test updates.** The leak-check behavior, tier gating, and mock canned responses are asserted in `tests/test_tutor.py` and `tests/test_flow.py`. Change a prompt → update the mock to mirror it and adjust the assertions in the same commit.
7. **Respect the honesty contract.** The profiler reports evidence ("consistent with O(n) at tested scales", R², confidence), never proofs. Don't add heuristics that convert low-confidence fits into confident classes.

## Conventions

- **Judge protocol:** `runner.py` writes `solution.py` + `cases.json` + a harness into a temp dir and executes it with a timeout. Case dicts: `{"args": [...], "expected": any, "label": str}`. Comparison is strict JSON equality with `sort_keys` — don't "fix" it to approximate float equality without updating README and tests.
- **Registries:** per-slug decorators in `judge/registry.py`: `@oracle(slug)` (correctness reference), `@judge_case(slug)` (small random cases with expected values), `@profiler_input(slug)` (worst-case-shaped inputs of size n — never early-exit inputs; see the random-bracket lesson in README).
- **Measurement protocol:** one timed call per subprocess; GC disabled around the call; tracemalloc started after module import; median across repeats. The subprocess boundary exists to contain hangs — don't replace it with in-process timing.
- **Curating a new problem:** add `function_name` + `visible_tests` to `data/problem_overrides.json`, a signature to `SIGNATURES` in `session/flow.py` (until signatures move into overrides in v0.3), and a generator/oracle pair in `judge/registry.py`. Then `dojo init` re-seeds.
- **Terminal-safe AI output:** tutor and reviewer prompts instruct plain text (no Markdown); `de_markdown` in `tutor/tutor.py` is the belt-and-braces cleanup applied at display time. Underscores are never stripped (they may be identifiers like `two_sum`); pin this with tests in `tests/test_tutor.py`.
- **Editor launching:** all `$EDITOR` behavior lives in `editor.py` — GUI editors detach via `Popen(start_new_session=True)`, terminal editors go through tmux/osascript, unknown editors block. Don't call subprocess directly from `flow.py`; tests cover the pure classification helpers only, never process spawning.
- **SQLite:** `db.py` owns schema and connection. Keep `sqlite3.Row` access by name. JSON columns go through `dumps_json`/`loads_json`.
- **CLI:** argparse subcommands in `cli.py`; each returns an exit code. Interactive flows read from `console.input` — tests use the `FakeConsole` fixture rather than real stdin.

## Definition of done

- `uv run pytest` passes; new behavior has tests.
- The never-solve boundary is unchanged or deliberately narrowed with rationale in the PR description.
- README updated when user-visible behavior changes (commands, ladder policy, grading semantics, limitations).
