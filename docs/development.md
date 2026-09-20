# Development

## Setup

```bash
make sync    # uv sync with a workspace-local UV_CACHE_DIR (.uv-cache)
make test    # uv run python -m pytest -q
make seed    # scripted first-run: dojo setup --user andy --skip-key --no-path
```

Python ≥ 3.13. Deps are managed by uv; add new ones with `uv add`, never by hand-editing the lockfile. **Always route uv through the Makefile targets (or set `UV_CACHE_DIR=$(pwd)/.uv-cache` yourself)** — the default uv cache lives outside the workspace and trips sandbox file policies. The test target uses `python -m pytest` so entry-script shebangs (which broke once after the repo was renamed) can never break it again.

## Hard rules

1. **Never-solve is architectural** — reference implementations must never enter tutor context; `tests/test_never_solve.py` pins the boundary.
2. **Copyright — private use** (see docs/curation.md).
3. **Secrets** — provider keys live in the environment or a gitignored `.env`; never logged, never in prompts/tests/fixtures.
4. **User data is real** — `data/dojo.db` and `workbench/` are personal state; migrations are additive only.
5. **Tests are offline and deterministic** — no network calls; always `MockBackend`; measurement tests target coarse outcomes (class, slope range), not exact timings.
6. **Prompt changes require test updates** — leak-check behavior, tier gating, and mock canned responses are asserted in `tests/test_tutor.py` and `tests/test_flow.py`.
7. **Respect the honesty contract** — the profiler reports evidence, never proofs.

## Conventions

- **Judge protocol:** case dicts `{"args", "expected", "label"}` plus optional verdict tags (`sorted` / `approx` / `rounded` / `predicate` / `ops`) — see docs/grading.md. Don't "fix" strict equality to approximate float equality without updating the docs and tests.
- **Measurement protocol (v0.12):** the probe runs the student and the reference interleaved, one subprocess per (target, size, repeat). Inside a subprocess: an untimed/untraced warm-up, **the timed call with no tracer running** (GC disabled, argument copy made *outside* the window), then a traced untimed space call. Never move the copy or the tracer into the timed region.
- **Never assert a complexity class from wall-clock timing.** The verdict rule is pinned on synthetic ratio series in `tests/test_growth.py`; `tests/test_probe.py` asserts mechanism properties (no tracer in the window, a constant-work function measures flat) and coarse outcomes. A timing-based class assertion flakes — one in `tests/test_flow.py` used to tolerate the very misclassification v0.12 removed.
- **SQLite:** `db.py` owns schema and connection; keep `sqlite3.Row` access by name; JSON columns go through `dumps_json`/`loads_json`.
- **Editor launching:** all `$EDITOR` behavior lives in `editor.py`; don't call subprocess directly from `flow.py`; tests cover the pure classification helpers only, never process spawning.
- **CLI:** each subcommand returns an exit code; interactive flows read from `console.input` — tests use the `FakeConsole` fixture (its `actions` hook simulates editing the workbench mid-session).
- **Terminal-safe AI output:** prompts require Markdown and `render_ai` renders it; `de_markdown` remains the legacy plain-text fallback; underscores are never stripped.
- **Fetcher:** the HTTP transport is an injected callable; tests pin the contract against canned GraphQL fixtures and never hit the network.
- **Static analysis:** radon + ruff run at submit as evidence; complexity > 10 is a flag, never a failure.

## Definition of done

- `uv run pytest` passes; new behavior has tests.
- The never-solve boundary is unchanged or deliberately narrowed with rationale.
- README/docs updated when user-visible behavior changes (commands, ladder policy, grading semantics, limitations).
