# HANDOFF — phase 14, the curricula rebuild

**Read this first. Then `AGENTS.md` (§0 is the branch discipline), `docs/curricula.md`
(the format), and `roadmap/v0.14.md` (the plan you are executing).**

Written 2026-09-27 on branch `curricula` (renamed from `v0.14-curricula` and pushed
to `origin`), at commit `3d0236e` + the commits that added this file. Delete this
file when phase 14 merges to `main`.

---

## 1. The situation

Two lines of work are live, and **you are on the rebuild line**:

| branch | what it is |
|---|---|
| `main` | the working trainer. The students practise here **every day**; the live database, the workbench and the debug log are here. Problem curation continues here, because the authoring commands still exist here. |
| `curricula` | this branch: splitting dojo into an **engine** (this repository) and **curricula** (their own repositories). Nothing that lands here is used for daily practice yet. |

The user's setup: one workspace on `main` for practice, and a **second workspace**
for this branch plus the curriculum repositories being built alongside it. You are in
that second workspace. `main` is the source of truth for the behaviour the rebuild
must preserve, and it will keep moving while you work (fixes, curation, small
corrections) — merge it in regularly.

**Do not touch `main`'s database.** If you point anything at the live DB, make it a
read-only copy first (§3).

## 2. What is done

Phase 14 is at **increment 0**: the documentation and the plan. No engine code has
changed on this branch yet.

- `README.md`, `AGENTS.md`, `docs/{architecture,curricula,grading,retention,development}.md`
  rewritten for the new perspective — the engine/curriculum split, the evidence
  model, and the four claims that define dojo.
- `curriculum-kit/` — the authoring interface, deliberately *not* engine code:
  `README.md` (the workflow), `AGENTS.template.md` (what a curriculum repository
  starts from), four prompts (`plan-a-curriculum`, `author-an-item`,
  `audit-a-curriculum`, `port-a-corpus`), and `example/` — a complete tiny
  curriculum (one measured item, one judged item, an alias, a real measurement axis).
- `roadmap/` — `README.md` (the arc), `v0.14.md` (this phase's plan, decisions and
  acceptance tests), `next.md` (phases 15–16 and the parked list), `history.md`
  (phases 1–13 condensed). The pre-split stage docs v0.1–v0.13 were retired on this
  branch; they live on `main`.
- Decisions taken (2026-09-25, plus one on 09-27) are recorded in `roadmap/v0.14.md`
  §7. Read them before proposing a change to the shape of anything.

## 3. Workspace setup

```bash
# this checkout is the branch; keep its state away from the live one
export DOJO_DATA_DIR=$PWD/.scratch/data            # scratch DB, logs, conf
export DOJO_CURRICULA_DIR=$PWD/.scratch/curricula  # enrolled curricula
export DOJO_WORKBENCH_DIR=$PWD/.scratch/workbench  # artifacts
export DOJO_NO_AUTO_UPDATE=1                       # no surprise pulls mid-session
UV_CACHE_DIR=$PWD/.uv-cache uv run pytest -q       # 546 tests, ~40 s, offline
```

`make test`, `make sync` and `make version` already set `UV_CACHE_DIR` for you.

**Testing against the real history** (the migration's acceptance test) means a copy,
never the original:

```bash
cp ~/path/to/main-checkout/data/dojo.db /tmp/dojo-live-copy.db
DOJO_DATA_DIR=/tmp/migrate-check uv run python -c "…"   # point the test at the copy
```

Re-take that copy **after every merge from `main`**: the live DB keeps growing, and a
stale copy proves nothing.

## 4. What to do next — increment A, in order

The plan is `roadmap/v0.14.md` §3 (increment A). The order matters, because the
corpus must never live in two places:

1. **The seam.** `src/dojo/curriculum/`: `manifest.py` (strict TOML → dataclasses),
   `validate.py` (every refusal in `docs/curricula.md` §8), `loader.py` (install,
   load, aliases, the two namespaces), `catalog.py` (tutor-safe view),
   `assessment.py` (quarantine: lazy, subprocess-only), `registry.py` (the generic
   decorators `curriculum-kit/example/assessment/*.py` already imports).
   `curriculum-kit/example/` is the target of the loader's tests: make it load, and
   make the tests fail if it stops exercising anything the format claims.
2. **The policy seam.** `scheduler.pick_new_problem` / `ladder_state` /
   `_prereqs_satisfied` walk *a curriculum's* topic graph and prereq edges instead of
   `patterns.PREREQS`; `_roadmap_groups` loses its process-wide cache. Keep
   `scheduler`'s FSRS half untouched.
3. **The schema**, additively: `curricula`, `curriculum_topics`, `enrollments`, the
   item columns, `evidence`, and the partial unique index on
   `(curriculum, external_id)`. Then the three renames under the protocol in
   `AGENTS.md` rule 6 — dry-run, backup, and the live-copy acceptance test.
4. **Neutral vocabulary in the engine** (`topic`, `item`, `outline`), with the
   curriculum supplying display words.
5. **The goldens.** Capture from `main` *after* your last merge: a session's picks,
   the outline render, the workbench path, the card keys. Then prove increment A did
   not change them.
6. **Increment B** (`roadmap/v0.14.md` §3): the NeetCode 150 repository built with
   `curriculum-kit/prompts/port-a-corpus.md` (its 161 files, 31 overrides, the
   registry content, the four duplicate pairs found by external id — see §4 of
   `roadmap/v0.14.md`), `dojo enroll/curricula/unenroll`, the picker, and the removal
   of the LeetCode content *and* the authoring tooling from this repository.

**Do not** implement phases 15/16 here: the evidence *model* lands in A (the record
and the kinds), but the gating/audit/conservative-scheduling behaviour is 15.A, and
JAX is 15.B. Generation is third-party by decision (rule 13) — the kit's prompts are
the engine's whole contribution.

## 5. The constraints that will bite you

- **Never-solve is now structural, not conventional.** Curriculum assessment code
  holds oracles and references. The loader's two namespaces (`catalog` /
  `assessment`) are what keep them away from the tutor; assert it as an *import graph
  per installed curriculum*, not a string grep (`AGENTS.md` rule 1).
- **The engine does not author content** (`AGENTS.md` rule 13). If you find yourself
  writing something that creates, curates, generates or fixes an item, stop: it
  belongs in `curriculum-kit/` or in a curriculum repository.
- **User data is real, and one migration is not additive** (rule 6). Renames need
  dry-run, backup, and the live-copy acceptance test — 15 cards reproducing from
  `rebuild_item_cards`, 37 attempts readable, no orphaned rows, no duplicate
  external ids. (Numbers from 2026-09-27; re-count them from the current copy and
  assert *those*.)
- **Behaviour preservation is the point of increment A.** No new student-facing
  capability, no new content, no editorial improvements to existing behaviour. If a
  refactor tempts you into fixing something, write it down for phase 15 instead.
- **The format is v1-unstable.** Change it when NeetCode 150 or JAX needs it; do not
  generalize for Rust (tabled) or for imagined curricula.
- **Tests stay offline and deterministic**, and never assert a performance class from
  wall-clock timing.

## 6. How you will know you are done

`roadmap/v0.14.md` §8 (definition of done), summarised:

- a fresh clone with nothing enrolled explains itself and enrolls in one command;
- with the NeetCode curriculum enrolled, the daily loop is indistinguishable from
  `main`, proven by goldens captured after the last merge;
- this repository contains no LeetCode content and no authoring tooling (a test
  asserts it);
- the migration's acceptance test passes against a fresh copy of the live database;
- `docs/` describes the engine and never a body of content;
- the never-solve import-graph test passes for every installed curriculum.

Then: bump the version, tag it (the major-epoch question is `roadmap/v0.14.md` §7 —
the recommendation is `1.14.0` + `git tag v1.14.0`), merge to `main`, and delete this
file.

## 7. Settled, and open

**Settled:** the major-epoch bump is taken — this branch is `1.x` (`1.13.N` while
phase 13 is the last completed phase), and phase 14 completes at `1.14.0` with `git
tag v1.14.0` on that commit. `version.py` finds the phase tag across majors, so the
count stays checkable (`1.13.11` = eleven commits since `v0.13.0`). One consequence
to expect: `PHASE_VERSION` is now `1.13`, so the debug-log marker mismatches once and
`data/logs/` is cleared.

**Open:**

- **Which curriculum next?** JAX is planned (phase 15.B). If another subject is
  wanted first, say so — the format is at its most changeable right now, and a second
  real user of it is what freezes v1.
- **The NeetCode 150 repository's location and visibility** (private, per the
  copyright rule; the fetcher and curator ports live with it).
