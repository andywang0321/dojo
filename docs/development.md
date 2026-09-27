# Development

## 1. Setup

```bash
make sync      # uv sync with a workspace-local UV_CACHE_DIR (.uv-cache)
make test      # the offline suite (uv run python -m pytest -q)
make seed      # scripted first-run: dojo setup --user andy --skip-key --no-path
make version   # write the version this commit will have into pyproject.toml (rule 10)
```

Python ≥ 3.13. Dependencies are managed by uv — add them with `uv add`, never by
hand-editing the lockfile. **Route uv through the Makefile targets, or set
`UV_CACHE_DIR=$(pwd)/.uv-cache` yourself**: the default cache lives outside the
workspace and trips sandbox file policies. The test target uses `python -m pytest` so
an entry-script shebang can never break it again.

## 2. Two lines of work

`main` is the trainer two people practise on **every day**; `curricula` is this
rebuild. `AGENTS.md` §0 has the rules; the mechanics:

- **Check the branch before every commit** — `git branch --show-current`. `make
  check-branch` (planned) runs the same check as a pre-commit hook. Rebuild work on
  `main` is the one mistake this phase cannot absorb.
- **Merge `main` into this branch regularly** (never rebase shared history), and
  treat the merged-in `main` as authoritative for the behaviour the rebuild must
  preserve. If a fix lands on `main` that this branch also needs, merge — do not
  cherry-pick silently.
- **Re-capture the goldens after the last merge.** The behaviour-preservation tests
  compare against a capture taken from `main` (session picks, outline render,
  workbench path, card keys). A golden captured before a merge is a stale oracle.
- **The live database is a moving target.** It keeps growing while this branch is
  open, so the migration is rule-based and re-runnable, and its acceptance test runs
  against a copy taken at merge time (§4).

## 3. Tests

Offline and deterministic, always: no network, `MockBackend` everywhere, and the
fixture curriculum (`tests/fixtures/curriculum-demo/`) as the loader's test double.

- **Never assert a complexity class from wall-clock timing.** The verdict rule is
  pinned on synthetic ratio series (`tests/test_growth.py`); `tests/test_probe.py`
  asserts mechanism (no tracer inside the timed window, a constant-work function
  measuring flat) and coarse outcomes. A timing-based assertion flakes — one used to
  tolerate the very misclassification the measurement rewrite removed.
- **Never let a test answer for a script that ran out.** `FakeConsole` raises rather
  than silently answering "quit", because a silent default once hid three
  under-specified tests.
- **Product-level tests drive `cli.main`** behind the `cli_env` fixture (temp DB,
  temp workbench, temp curricula directory, canned console input).
- **The never-solve test is an import graph**, per installed curriculum, not a string
  grep: if anything on the tutor path can reach `assessment`, the suite fails.
- A curriculum's own evaluators are tested in its own repository, under the same two
  rules (offline, no timing-class assertions).

## 4. Migrations

Additive by default: `ALTER TABLE … ADD COLUMN` or a new table, and `migrate()`
reconciles a migrated database against a fresh one column-for-column (a test asserts
it, because the old hand-kept ALTER list left old databases permanently short of the
schema with nothing able to notice).

**The one exception this phase allows** is the three renames
(`problems`→`items`, `problem_id`→`item_id`, `pattern`→`topic`), and it is
protocol-bound:

1. `dojo migrate --dry-run` prints every statement it would run and touches nothing.
2. A backup of `data/dojo.db` is mandatory before the real run; the path is printed.
3. The migration is a rule, not a list: rows map to a curriculum by the rule stated
   in `roadmap/v0.14.md` §4, so a database that grew since the last test still
   migrates correctly.
4. `tests/test_migration_live_db.py` copies the live database, migrates the copy and
   asserts: the cards reproduce bit-for-bit from `rebuild_item_cards`, every attempt
   is readable with its statement, nothing is orphaned, and no
   `(curriculum, external_id)` pair collides.
5. If it cannot satisfy all four, it stays additive instead.

## 5. Adding a mechanism to the engine

Ask the seam questions in `AGENTS.md` §5 first. Then:

- **A new AI role** — `Role` in `tutor/backend.py`, a budget in `ROLE_BUDGETS`
  (tokens, temperature, timeout), a mock entry, and a routing test. A curriculum may
  not add one.
- **A new verdict mode** — `judge/compare.py` (one implementation, shared by the
  judge and the reference gate), the case vocabulary in `docs/curricula.md` §4, and
  the tests in `tests/test_judge*.py`. A curriculum cannot invent one; it can only
  use what is implemented.
- **A new evidence kind** — `evidence.py` plus the strength table in
  `docs/grading.md` §1, plus what the display does with it. Never a kind without a
  strength, and never a strength that inflates a weaker kind.
- **A new measurement statistic** — the framework in `measure/`, the plan field a
  curriculum may request in `docs/curricula.md` §5, and a mechanism test.
- **A new path or env var** — `config.py`, documented in `AGENTS.md` §7, and
  redirected in `tests/conftest.py` **before dojo is imported**. Read paths at module
  scope; an in-function import re-reads the module attribute and silently escapes
  every monkeypatch.

## 6. Adding a curriculum

Authoring is third-party (see [curricula.md](curricula.md) §10 and the
`curriculum-kit/` directory), and the engine's side of it is deliberately small: it
enrolls, validates, imports and runs. The engine-side work when the format changes is
to keep `curriculum-kit/example/` exercising every feature the format claims, because
that example is the format's executable specification and the loader's test double.

To test a curriculum change end to end without touching the real state:

```bash
DOJO_DATA_DIR=/tmp/dojo-check \
DOJO_CURRICULA_DIR=/tmp/dojo-check/curricula \
DOJO_WORKBENCH_DIR=/tmp/dojo-check/workbench \
uv run dojo enroll ./my-curriculum
```

The three directories are independent on purpose: moving the curricula directory
never moves the database, and vice versa.

## 7. The version ritual

The version is `<major>.<phase>.<commit>`; `pyproject.toml` carries it and git proves
it. `make version` writes the version of the state you are in — with uncommitted work,
the number that work will be committed as; on a clean tree, the current one.
`tests/test_version.py` accepts exactly two values (HEAD's, or the commit in flight)
and fails otherwise with "run `make version`", so a forgotten bump is caught by the
suite rather than by a stale shell prompt.

The third component counts commits since the last phase tag **on the branch you are
on**, so `main` and this branch show different counts off the same tag. That is
expected, not drift.

**Completing a phase** is `make version` plus two manual touches in one commit: set
`pyproject.toml` to the phase version (`<major>.<phase>.0`) and `git tag
v<major>.<phase>.0` on that commit. The tag is what the next phase's commits count
from.

**The epoch bump is taken (2026-09-27): dojo is `1.x`.** Phase 14 completes at
`1.14.0` + `git tag v1.14.0`, and until then this branch is `1.13.N` while `main` is
`0.13.N` off the same tag. The bump is a hand edit to the major only; `version.py`
finds the phase tag across majors (it tries `v<major>.<phase>` first, then any major
carrying that phase), so the count stays checkable against git either way. Because
`PHASE_VERSION` changes from `0.13` to `1.13`, the debug-log marker mismatches once
and `data/logs/` is cleared — the same thing a phase completion does, and the reason
the log is version-gated at all.

## 8. Do-not-break list

These are behaviour-preservation requirements, and each has a test:

- The daily loop's student-visible behaviour: picks, the outline render, the
  workbench path, the card keys, the session's prompts and pointer lines.
- `run_cases` never raises; an empty case list is refused; a raised case is
  `status="error"`.
- The measurement never fits an absolute curve, and `unresolved` never reddens a
  claim.
- A network failure is reported as the network, an answered error keeps its
  technical line, and every request carries its role's timeout.
- `quit` records nothing; an attempt exists iff the student submitted; the warm-up
  grade is one transaction.
- Cards are rebuildable by replay, and the live database's 15 cards reproduce
  exactly after the migration.
- The never-solve import graph, per curriculum.
- `data/` and the real workbench are byte-identical after a full test run.

## 9. Definition of done

- `uv run pytest` passes, offline, and new behaviour has a test that fails before the
  change (state that in the commit message).
- The never-solve boundary is unchanged, or narrowed deliberately with the rationale
  written down and pinned by a test.
- `README.md` and the matching `docs/` file are updated in the same commit — a change
  that makes a doc wrong is an incomplete change.
- Phase work lands in `roadmap/`; a decision that shapes the future gets written into
  the phase doc's decisions section, not just into chat.
