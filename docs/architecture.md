# Architecture — the engine

*This document describes the engine as the curricula split lands (phase 14). The
session loop, the workbench views, the judge protocol, the measurement framework and
the AI boundaries are already true of `main`; the `curriculum/` package, the
evidence record and the curriculum-aware schema arrive with increment A. Where a
paragraph describes the target, it says so.*

## 1. The loop

Four claims drive one loop (`README.md` §intro): **spaced repetition**, **evidence**,
**AI personalization**, **AI curriculum generation**.

```
        ┌─────────────────────── curriculum (a repository) ──────────────────────┐
        │  topics · items · checks · assessment · measurement policy · display   │
        └───────────────────────────────┬───────────────────────────────────────┘
                                        │ catalog            assessment (quarantined)
                                        ▼                              ▼
  schedule ──▶ session ──▶ submission ──▶ evidence ──▶ schedule        judge / measure
  (FSRS)      (one loop,   (artifact)     (kind +      (grades,        (subprocesses)
              two phases)                 strength)    intervals)
                                        ▲
                        AI agents ──────┘  tutor · teacher · reviewer · auditor · curator
```

Nothing in the loop knows what the subject is. The curriculum supplies content and
policy; the engine supplies mechanism.

## 2. What crosses the seam

| the engine provides | the curriculum declares |
|---|---|
| FSRS-4.5 scheduling, the due queue, the daily budget | the topic graph and prerequisite edges |
| the session state machine, the workbench and artifact views | the artifact template and its interpreter |
| the judge harness (isolation, protocol, verdict modes) | oracles, generated cases, references, visible checks |
| the measurement framework (paired, ratio-based, uncertainty stated) | what to measure, on which axis, against which baseline |
| the AI roles, budgets, guards, provenance | rubrics and topic primers for its own subject |
| the evidence record, its tiers, its disclosure rules | which evidence kind each item can produce |
| enrollment, storage, display, the CLI | its display vocabulary and difficulty labels |

The full format is [curricula.md](curricula.md).

## 3. Modules

```
src/dojo/
  curriculum/       # the seam (NEW in phase 14)
    manifest.py     # strict curriculum.toml -> dataclasses; unknown keys are errors
    validate.py     # every refusal in curricula.md §8, all reported, never the first
    loader.py       # install/load/aliases; exposes catalog and assessment separately
    catalog.py      # tutor-safe view (see §4)
    assessment.py   # lazy, subprocess-only: oracles, cases, references, rubrics
    registry.py     # the decorators assessment modules register with
  evidence.py       # tiers, provenance, gates vs advisories, the audit policy (NEW)
  db.py             # schema + reconciling migrate() + queries
  bank.py           # a curriculum's catalog -> item rows, and the prune
  scheduler.py      # FSRS-4.5, cards, due queue, enrollment-aware picks
  judge/runner.py   # artifact + cases + harness in a temp dir, bounded and isolated
  judge/compare.py  # per-case verdict semantics (shared with the reference gate)
  measure/probe.py  # paired measurement, medians, per-size records
  measure/growth.py # the ratio trend -> a class relative to the reference, or unresolved
  session/state.py  # workbench/<curriculum>.<item>.state.json; tolerant loads
  session/workbench.py  # artifact rendering + student_view() for every AI reader
  session/flow.py   # run_day: ONE loop, phase-driven; run_warmups
  session/learn.py  # the teacher conversation + practice handoff
  tutor/backend.py  # Role-keyed protocol; OpenAI-compatible + Anthropic + mock
  tutor/{tutor,reviewer,prompts}.py
  cli.py config.py guard.py proc.py debuglog.py version.py editor.py terminal.py
  render.py ui.py updater.py
curriculum-kit/   # the authoring interface (NOT engine code): the example
                  #   curriculum, AGENTS.template.md, and four agent prompts
```

## 4. The loader and the two namespaces

`loader.load(id)` returns a `LoadedCurriculum` with two attributes:

- **`.catalog`** — topics, items, statements, artifact templates, visible checks,
  display vocabulary, measurement *plans*. This is what the session, the workbench,
  the outline view and the CLI read.
- **`.assessment`** — oracles, generated cases, references, rubrics, hidden
  checkers, measurement implementations. Loaded lazily, on first use, inside a
  subprocess; never imported by the engine's module graph.

The tutor's context is assembled from a fixed field list — statement, the student's
code as `student_view` renders it, the tier, the hint history — so the boundary is
not "the tutor happens not to look": the prompt builder has no accessor that could
return assessment material. `tests/test_never_solve.py` asserts it as an import
graph per installed curriculum, and the fixture curriculum exercises it.

Validation is strict and total (`curricula.md` §8): unknown manifest keys, dangling
file references, graph cycles, duplicate ids, a duplicate `external_id`, an
`executable` item with no oracle, an `assessment` module importing beyond its
allowances, a dropped topic with history and no `retired` marker.

## 5. Data model

*Target shape. `problems`→`items`, `problem_id`→`item_id`, `pattern`→`topic` are
renames, performed under the protocol in `AGENTS.md` rule 6 (dry-run, backup, and a
test against a copy of the live database).*

- `users(name)` — one row per person; everything is per-user.
- `curricula(id, title, version, source, commit, installed_at, format, manifest_json)`
  — installed curricula, mirrored from disk and re-validated on import.
- `curriculum_topics(curriculum, topic_id, title, position, prereqs JSON)` — the
  graph, as data. `UNIQUE (curriculum, topic_id)`.
- `items(curriculum, item_id, topic, title, difficulty, external_id, statement,
  artifact_path, function_name, visible_tests, signature, expected_time,
  expected_space, evidence_kind)` — the catalog, mirrored from a curriculum.
  `UNIQUE (curriculum, item_id)`, plus a partial unique index on
  `(curriculum, external_id) WHERE external_id IS NOT NULL`.
- `enrollments(user_id, curriculum, enrolled_at, active, settings JSON)` —
  enrollment is a flag, never a delete. Un-enrolling pauses serving and keeps every
  row.
- `attempts(user_id, item_id, kind[solve|warmup], code, status, …, recall_grade,
  ai_provenance, curriculum_version)` — the learner model. **A row exists iff the
  student submitted**: created on the first submit (pass or fail, with the judge's
  verdict as `status`), updated by later submits in the same session, and never
  created by a session that was only started. `quit` records nothing.
- `attempt_revisions(attempt_id, revision, code, claims, measurement, static JSON,
  review, judge_summary)` — every submitted version with the artifacts *that*
  version produced. A re-submit appends; the head keeps the newest raw artifact so
  older queries keep working.
- `evidence(attempt_id, revision, kind, source, strength, verifier, payload JSON,
  unresolved, produced_at)` — **new**: one row per piece of evidence, so the tiers
  in [grading.md](grading.md) are queryable and disclosed rather than implied by
  which columns happen to be non-null.
- `item_cards(user_id, curriculum, item_id, topic, stability, difficulty, reps,
  lapses, due_at, last_review_at, last_reflection, evidence_kind, created_at)` — one
  card per solved item, keyed by curriculum so two curricula may both have a `stack`.
  Derived state: `rebuild_item_cards` replays the attempt log, which is how the
  migration proves itself.
- `learn_sessions(user_id, curriculum, topic, transcript JSON, created_at, completed)`
  — one row per learning-mode session, rewritten after every exchange.
- `pattern_cards` — legacy, no longer written, kept as a record.

`data/dojo.db`, `data/logs/`, `data/dojo.conf`, `data/curation/` and the workbench
are user state (see `AGENTS.md` §7). Migrations are additive by default and
`migrate()` reconciles a migrated database against a fresh one column-for-column.

## 6. The evidence record

Every piece of evidence has a **kind** (`executable`, `measured`, `static`,
`judged`, `self_report`, and later `peer`), a **source** (which judge, probe, tool or
agent produced it), and a **strength** derived from the kind. Displays read the
strength; the scheduler reads it too, conservatively (`retention.md` §3). Advisories
and gates are different things: a review that shapes what you read is advisory; a
judgment that would mark a unit complete or let an interval grow is a gate and needs
an independent audit pass, with disagreement recorded as `unresolved` rather than
smoothed over. The full model is [grading.md](grading.md).

## 7. The session

One loop, two phases, both persisted so a crash resumes in the right mode:

| | solving (agent = tutor) | solving (agent = discussion, after `polish`) | post_solve |
|---|---|---|---|
| `open` / `check` | ✓ | ✓ | — (pointer to `polish`) |
| `submit` | judge; on pass → post_solve | re-grade, new revision, → post_solve | — (pointer) |
| `polish` | — (pointer) | — | → solving, agent stays discussion |
| `learn` / `report` | ✓ | `report` ✓; `learn` explains it is done | — |
| `quit` | abandon (records nothing) | keep the attempt, end | — |
| `done` | — | — | end the session |
| anything else | question → tutor (leak-audited) | question → discussion | question → discussion |

A command that does not belong to the phase gets a pointer line instead of being
sent to the model as a question. `polish` is a **mode switch**, not a re-grade: the
never-solve boundary lifts at the first passing submit and cannot be put back, so
polishing is editing with the post-solve agent answering.

**The artifact and its views.** `session/workbench.py` renders the artifact from the
curriculum's template: shebang (dojo's venv, or the interpreter the curriculum
declares), the statement, the stub, and a fenced `if __name__ == "__main__"` block
generated from the item's own visible checks. Six readers, one file, and that module
owns the difference — the student sees everything, the AI agents and the static
layer see `student_view()` (dojo's chrome stripped, the student's edits preserved),
and `dojo show` keeps the raw artifact with `--clean` for the AI's view. Neither the
judge nor the measurement executes the examples block: both load the artifact under
a name that is not `__main__`, pinned by a test. A template that does not compile is
refused rather than written.

**Warm-ups.** `run_warmups` serves the due queue, which is global across enrolled
curricula and labelled per curriculum. The curriculum's warm-up policy decides what
the session asks for (`re-solve`, `re-derive`, `re-justify`); retiring state,
grading, the card update and the lapse rule belong to the engine.

**Enrollment and the picker.** Reporting commands are global; only session commands
(`dojo`, `dojo <item>`, `dojo warmup`, `dojo learn`) resolve *which curriculum*,
asking once and remembering the answer. `--curriculum <id>` is the escape hatch for
scripts.

## 8. The judge harness

`judge/runner.py` writes the artifact, the case list and a harness into a temp dir
and runs it under a timeout. The harness swaps **both** `sys.stdout` and file
descriptor 1, bounds output on both sides, reads the last parseable line, and the
parent runs the child in its own process group with rlimits so a timeout kills
grandchildren too. `run_cases` never raises and refuses an empty case list.

A case is `{"args": […], "expected": …}` plus optional verdict tags — `compare:
sorted` (any-order outputs), `compare: approx:1e-4` / `rounded:n` (floats),
`predicate: <checker>` (property checks), `ops: […]` (stateful class APIs). Default
is strict JSON equality with sorted keys; a case that **raised** is
`status="error"`, not `wrong_answer`. `run_cases(..., python=…)` is the interpreter
seam: a curriculum with its own environment points it at that interpreter, which is
how a JAX curriculum gets `jax` without the engine depending on it.

A curriculum cannot invent a verdict mode: the vocabulary is the engine's, so a tag
the judge does not implement is a validation failure rather than a silently ignored
hint.

## 9. The measurement framework

Method (engine): one measurement per subprocess, medians across repeats, an untimed
warm-up, the timed call with **no tracer running**, then the space call with
tracemalloc active and untimed; every call gets a fresh deepcopy of its arguments so
in-place mutation cannot leak between sizes.

Verdict (engine): the student and a paired reference are measured **interleaved at
each size**, and the ratio trend becomes a class *relative to the reference*, or an
explicit `unresolved`. A ratio cancels everything the two share, which is why one
class of difference is decidable here and was not decidable from a single fitted
curve — v0.11's absolute fit could not separate `O(n)` from `O(n log n)` at feasible
sizes, and its honest output was a bracket nobody could use. **Never reintroduce it.**

Policy (curriculum): the axis, the size ladder, the baseline (a canonical reference,
or a deliberately naive one — which is what makes "jitted vs the same loop in
Python" a meaningful claim), extra statistics, and the comparison mode for outputs.
An item with no policy is reported as *not measured*; a policy that declines is
reported as *not measurable here*.

## 10. AI roles and boundaries

Roles: `tutor`, `discussion`, `teacher`, `reviewer`, `auditor` (leak check), and —
with the evidence model — a review auditor. The authoring roles (`curator`,
`curation_auditor`, `referencer`) do not exist here: authoring is third-party
(`curriculum-kit/`). Every call names its role, and the role decides the request's system
prompt, model, token budget, temperature, timeout and provenance record. Providers:
DeepSeek (OpenAI-compatible), OpenAI (same wire) and Anthropic (its own wire, JSON
via a forced tool call). A curriculum cannot add a role.

Boundaries: every AI and subprocess call runs behind `guard`, network failures are
reported as the network (classified by name, never by importing an SDK), answered
errors keep their technical line, every request carries its role's timeout, and the
client carries one retry. The tutor never receives reference material or
topic-canonical code; the teacher's documented narrowing (topic + conversation only)
is the one exception and stays pinned by its test.

## 11. Paths

| path | env | holds |
|---|---|---|
| `REPO_ROOT` | — | the engine: code, docs, roadmap, the fixture curriculum |
| `config.CONTENT_DIR` | — | engine-shipped content (the fixture, templates) |
| `config.DATA_DIR` | `DOJO_DATA_DIR` | user state: DB, logs, conf, curation scratch |
| `config.CURRICULA_DIR` | `DOJO_CURRICULA_DIR` | installed curricula (`~/.local/share/dojo/curricula/<id>/`) |
| `config.WORKBENCH_DIR` | `DOJO_WORKBENCH_DIR` | the editor/debugger workspace (`~/.local/share/dojo/workbench/`) |

The engine's own virtualenv is what the artifact shebang points at unless a
curriculum declares its own interpreter; `ipykernel` and `debugpy` ship with the
engine so notebook kernels and the debug adapter exist everywhere.

## 12. Extension points and deliberate gaps

**Extension points (v1):** the manifest (content and policy), assessment modules
(evaluators), measurement policies, display vocabulary, aliases. There is no
curriculum-supplied CLI: a curriculum's own scripts live in its repository, and the
engine's curriculum surface is enrollment plus a read-only audit.

**Deliberate gaps, documented rather than built:**

- **A multi-file artifact** (a Rust crate: `Cargo.toml` + `src/` + `tests/`). The
  artifact is one file because every planned curriculum is one Python file; the
  runner interface (`run_cases`, a command spec) would carry it, but the rendering,
  the state path and the IDE story would all need a tree. Rust is tabled.
- **A non-Python runner.** `run_cases(..., python=…)` swaps the interpreter; a
  compiled toolchain's runner is a different implementation with a diagnostics-shaped
  verdict vocabulary (`compile_failed`, error codes) that the case model does not
  express.
- **A plugin API beyond the format — and no authoring API.** Curricula declare
  content, policies and evaluators; they cannot add CLI nouns, AI roles or scheduler
  behaviour. Authoring is third-party by design: the engine's authoring surface is
  the specification, `dojo enroll` as the validator, and the importable
  `dojo.curriculum` package for an external tool that wants to validate or render
  without going through the CLI. The format is v1-unstable, not a public contract with
  a deprecation policy, until two real curricula use it.
- **Remote or multi-machine state.** One computer, one user, by design.

## 13. Known limitations

- The measurement reports growth *relative to a reference*; without one it reports
  only durability at scale, and says so.
- Items whose output grows exponentially (or whose growth is flat, or fixed-size)
  have no meaningful size ladder: their policy declines and the column reads *not
  measurable here*.
- Comparing outputs at scale compares one input per size: a free side-check, not a
  substitute for the judge's cases. Randomized fuzzing with shrinking remains
  backlog.
- The judge's default comparison is strict JSON equality (`1.0` vs `1` differ);
  per-case comparators are how "any order" and float tolerance are expressed
  honestly.
- Judge timeouts bound a session; a slow-but-correct solution can time out at scale
  and is reported as such rather than scored.
- The teacher has no oracle behind it: pedagogy is unverified by construction, and
  the prompt says so. Transcripts are stored but not resumable across sessions.
- Terminal editors detach only inside tmux or on macOS; elsewhere `open` falls back
  to blocking.
- A curriculum's own evaluators are tested in its own repository: the engine can
  guarantee isolation and honest reporting, not that someone else's checks are good.
