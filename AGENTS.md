# AGENTS.md — working on the dojo engine

Guidance for humans and AI agents working in this repository. This checkout is the
**engine**, not a curriculum: it schedules practice, produces evidence, and hosts
the AI agents. What you practise comes from a curriculum, which lives in its own
repository.

Read this file first, then `README.md` (the user-facing pitch), `docs/curricula.md`
(the format — the seam everything else hangs off), and `roadmap/v0.14.md` (the
phase in flight).

---

## 0. Which branch are you on? (read before every commit)

**This repository has two live lines of work, and this is the rebuild line.**

| branch | what it is | who is on it |
|---|---|---|
| `main` | the working trainer: the students practise here **every day**, on the NeetCode 150 curriculum | daily use; bug fixes, problem curation, small corrections |
| `v0.14-curricula` | the curricula rebuild: splits the engine from the curriculum, moves NeetCode 150 out | this phase's work |

Rules, in order of severity:

1. **Before committing, run `git branch --show-current` and read it.** Rebuild work
   must never land on `main`; a fix meant for the live trainer must never land only
   here. If the answer is not the branch you meant to be on, stop — do not commit,
   and do not "fix it up in the next commit".
2. **No breaking feature work on `main`.** `main` is a product two people use
   daily: bug fixes, curation, doc corrections and other non-breaking changes are
   fine; nothing that changes the shape of the schema, the curriculum assumption,
   or the CLI contract of an existing command.
3. **`main` is not frozen and will drift.** Merge `main` into this branch regularly
   (never rebase a shared branch), and treat the *current* `main` as the source of
   truth for the behaviour the rebuild must preserve. The live database keeps
   growing while this branch is open, so the migration is **rule-based and
   re-runnable**, never a snapshot script (see `roadmap/v0.14.md` §4).
4. **The rebuild lands as one phase boundary.** Phase 14 completes when this branch
   merges to `main` with the version bumped and tagged in the same commit (rule 10).
   Until then `main` keeps serving practice.

`make check-branch` (planned with increment A) will run the same check as a
pre-commit hook so it cannot be skipped by accident; until it exists, the check is
manual and mandatory.

---

## 1. What dojo is

dojo is a local practice engine built on four claims:

1. **Spaced repetition** — FSRS-4.5 over what you actually practised decides what
   comes back and when.
2. **Evidence** — dojo produces the strongest honest evidence it can about what you
   just did, states its strength, and lets *only that evidence* move the schedule.
   Never a claim the evidence does not support; "unresolved", "unjudged" and "not
   measurable here" are first-class outcomes.
3. **AI personalization** — a coach that guides and never solves, a teacher for
   topics you have not met, a reviewer that critiques what you wrote.
4. **AI curriculum generation** — a curriculum can be *bootstrapped* from a source
   you trust (a problem set, a library's own documentation) and then tailored to
   you, because you are not expected to be an expert in the thing you are trying to
   learn. **This one happens outside the engine** (rule 13): dojo ships the
   specification and the agent kit; it does not build curricula.

The formula is a loop, not a list: practice produces evidence, evidence moves the
schedule, the schedule chooses the next practice, and the agents adapt the
curriculum around it.

Corollary — the sentence that decides most design questions here:
**dojo is the engine; a curriculum is what you practise.** Anything that only makes
sense for one body of content belongs in that curriculum's repository, not here.

## 2. What this repository is, and what it is not

**Is:** the scheduler (FSRS), the session loop and its state machine, the workbench
and its artifact views, the judge harness (subprocess isolation, verdict modes, the
JSON protocol), the measurement *framework* (paired measurement, ratio-based
verdicts, stated uncertainty), the AI roles and their boundaries, the evidence
record, enrollment, the CLI, the SQLite schema and its migrations, the debug log,
the version, the IDE/debugging story.

**Is not:** any problem statement, any test corpus, any oracle or reference
solution, any topic taxonomy, any ladder, any language-specific intake, any
progression *policy* — and **no authoring, curation or generation tooling**. Content
lives in a curriculum repository and arrives through the loader; content *tooling*
lives with it, guided by `curriculum-kit/`. The engine ships exactly one curriculum,
`curriculum-kit/example/`, which is the format's executable specification, the
loader's test double, and the skeleton a new curriculum copies.

## 3. Layout map (target — increment A brings it about)

```
src/dojo/
  cli.py            # argparse entry; bare `dojo` = the daily routine; custom HELP_TEXT
  config.py         # paths, env, PROVIDERS, DOJO_MODEL[_<ROLE>], DOJO_TIMEOUT,
                    # DATA_DIR (user state) vs CURRICULA_DIR (user content)
  curriculum/       # NEW: the seam
    manifest.py     # curriculum.toml -> dataclasses, strict
    validate.py     # every refusal in docs/curricula.md §Validation
    loader.py       # install/load/alias resolution; the two namespaces
    catalog.py      # tutor-safe view: topics, items, statements, templates, display words
    assessment.py   # QUARANTINE: checks, oracles, generators, references, measurement
    registry.py     # the generic decorators an assessment module registers with
  evidence.py       # NEW: tiers, provenance, gates vs advisories, the audit policy
  db.py             # schema + reconciling migrate() + queries; MIGRATIONS ADDITIVE
  bank.py           # item importer: a curriculum's catalog -> rows (prunes both ways)
  scheduler.py      # FSRS-4.5, cards, due queue, enrollment-aware picks
  judge/            # runner (isolation, protocol) + compare (verdict semantics)
  measure/          # the paired-measurement framework + the growth verdict rule
  session/          # state machine, workbench/artifact views, flow, learn
  tutor/            # backend (roles/budgets/timeouts) + prompts + hint ladder + reviewer
  editor.py terminal.py render.py ui.py proc.py guard.py debuglog.py version.py
curriculum-kit/     # the authoring interface (NOT engine code): the example
                    # curriculum, AGENTS.template.md, and the agent prompts
tests/              # offline suite; the example curriculum is the loader's double
docs/               # architecture, curricula, grading, retention, development
roadmap/            # README (index), v0.14.md (this phase), next.md, history.md
```

Gone from this repository once increment B lands: `problems/`,
`data/roadmap.toml`, `data/problem_overrides.json`, `patterns.py`, `fetcher/`, the
LeetCode content of `judge/registry.py`, and `curator/` — the content and the
authoring tooling both leave, the first to a curriculum repository and the second to
that repository or to a separate authoring project built on `curriculum-kit/`.

## 4. Hard rules

1. **Never-solve is structural.** A curriculum ships reference solutions, oracles
   and generators — exactly the material the tutor must never see. The loader
   therefore exposes **two namespaces**: `catalog` (statements, templates, topic
   metadata — tutor-safe) and `assessment` (checks, oracles, references,
   measurement — quarantined). The tutor path may import only `catalog`; assessment
   code is loaded lazily, runs only inside a bounded subprocess, and is never
   reachable from a prompt builder. `tests/test_never_solve.py` asserts this as an
   **import graph per installed curriculum**, not as a string grep. The one
   documented narrowing stays the v0.8 teacher (topic + conversation only).
2. **Copyright and privacy.** dojo is a private-use tool: the students' own data,
   the live database, the workbench and the debug log are never published, quoted in
   a public issue, or committed. Curricula *are* meant to be publishable — which is
   why a curriculum declares its `license`, why `license = "private"` means "never
   publish this", and why material drawn from a paid or proprietary source (a
   course's problem set, a book's exercises) belongs in a private curriculum
   repository only. Never publish a curriculum whose source you do not have the
   right to redistribute, and never let a bootstrap ingest a source whose terms
   forbid it.
3. **Secrets.** Provider keys (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`,
   `ANTHROPIC_API_KEY`, or their `DOJO_`-prefixed aliases) live in the environment
   or a gitignored `.env`. Never log one, never put one in a prompt, a test, a
   fixture or a curriculum manifest.
4. **Curriculum code is external and untrusted.** The engine imports no curriculum
   at module scope, executes assessment or tool code only through `proc.run_capped`
   with child limits, and validates a manifest loudly before use. A curriculum can
   add content and evaluators; it can never add an AI role, reach the tutor
   context, or change the scheduler.
5. **Evidence honesty.** Every piece of evidence records its kind, source and
   strength (`docs/grading.md`). Machine-checked beats measured beats judged beats
   self-reported, and the display says which. An AI judgment is **advisory** unless
   it gates something, and a gating judgment needs an independent audit pass. An
   unreachable AI never blocks the loop: the work is recorded as *submitted,
   unjudged*, scheduled from the self-report, and disclosed. Never launder weak
   evidence into a stronger claim; never claim a measurement the ratio does not
   support; never reintroduce an absolute curve fit (v0.11's `fit.py` is the
   cautionary tale).
6. **User data is real, and one migration in this phase is not additive.** Schema
   changes are additive by default, and `migrate()` reconciles a migrated DB
   against a fresh one column-for-column. The split needs three **renames**
   (`problems`→`items`, `problem_id`→`item_id`, `pattern`→`topic`); SQLite supports
   renames in place, so the exception is allowed but protocol-bound: a `--dry-run`,
   a mandatory backup, and a test that runs the whole migration against a **copy of
   the live database** and proves the attempt history and the replayed cards are
   intact. Anything that cannot satisfy that protocol stays additive.
7. **Tests are offline and deterministic.** No network; `MockBackend` everywhere;
   `curriculum-kit/example/` is the loader's test double. **Never assert a class from
   wall-clock timing** — the verdict rule is pinned on synthetic ratio series
   (`tests/test_growth.py`) and `tests/test_probe.py` asserts mechanism. A
   curriculum's own evaluators get the same treatment in its own repository.
8. **Prompt changes require test updates in the same commit.** Role routing is by
   `Role`, never by prompt text, so wording is free — the assertions that depend on
   behaviour are not.
9. **Every AI and subprocess call runs behind a boundary.** `dojo/guard.py` turns a
   transport or API failure into one printed line, a `degraded` debug-log event and
   a session that keeps going. Network failures are reported as the network
   (`is_network_error` / `network_message`, classified by name and never by
   importing an SDK), an answered error (401/429/5xx) keeps its technical line,
   every request carries its role's timeout, and the client carries one retry.
10. **The version is `<major>.<phase>.<commit>`; `pyproject.toml` carries it and git
    proves it.** `make version` writes the version of the state you are in, and
    `tests/test_version.py` accepts exactly two values (HEAD's, or the commit in
    flight) and fails otherwise with "run `make version`". The third component counts
    commits since the last phase tag **on this branch**, so the two branches show
    different counts off the same tag — expected, not drift. Phase 14 completes by
    setting `pyproject.toml` to the phase version and tagging that commit; the major
    is a manual epoch bump and this phase is the natural place for one (see
    `roadmap/v0.14.md` §7).
11. **Identity is `(curriculum, item)` with an optional external id.** Two rows may
    never share an `external_id` inside one curriculum — an invariant the schema
    enforces, because the live bank still carries four LeetCode problems twice
    (curated under one name, dead under another) and the roadmap's curated/missing
    flag was decided by dict-iteration order as a result. Renames are declared in
    the manifest's `aliases`, and a manifest that drops a topic or item **with
    history** warns and keeps that history addressable rather than silently
    orphaning it — the same stance as the bank prune.
12. **Docs are part of the product.** This file, `README.md` and `docs/` describe
    the engine and never one body of content. Curriculum conventions (LeetCode
    intake, JAX measurement, a curriculum's own oracle style) live in that
    curriculum's repository. A change that makes a doc wrong is an incomplete
    change.
13. **The engine does not author content.** No curriculum creation, item curation,
    generation or repair in this repository. The engine's entire curriculum surface is
    `dojo enroll` (install + validate + enroll; re-enrolling is how it updates),
    `dojo curricula` (list), `dojo unenroll` (pause), and `dojo report` (read-only
    audit). Authoring tooling lives in a curriculum repository, guided by
    `curriculum-kit/` in this one — the spec, the example, the AGENTS template and
    the agent prompts. If a change here would create, curate, generate or fix
    content, it belongs in that kit or in a curriculum repository instead. The
    corollary matters for the seam: because authoring is external, the engine must
    keep its *enforcement* honest (validation, the two namespaces, the evidence
    kinds) rather than assuming a well-meaning author on the other side.


## 5. The curriculum seam: how to add capability without breaking it

The seam is `docs/curricula.md`. Three questions decide where new code goes:

- **Does it only make sense for one body of content?** → the curriculum repository.
- **Is it a *policy* (which topic next, what to measure, what "pass" means)?** →
  declared in the manifest, implemented by the curriculum.
- **Is it a *mechanism* (isolation, scheduling math, evidence storage, prompting,
  display)?** → the engine.

Two standing cautions, both earned:

- **Do not generalize ahead of the second implementation.** The format is **v1 and
  explicitly unstable** until two real curricula (NeetCode 150 and JAX) use it.
  Rust — the case that would break the "the artifact is one Python file" and "the
  runner is Python" assumptions — was deliberately tabled; the seams it would need
  are documented as gaps in `docs/architecture.md`, not built.
- **Do not let the engine learn a curriculum's words.** Core vocabulary is
  curriculum → topic → item → attempt → evidence → card. A curriculum supplies its
  display words (`Ladder`, `Pattern`, `Module`) and its own difficulty labels.

## 6. AI providers

`config.PROVIDERS` is the table: DeepSeek (OpenAI-compatible, `api.deepseek.com`),
OpenAI (same wire, SDK default base URL) and Anthropic (its own messages wire:
top-level `system`, no `response_format`, JSON via a forced `emit_json` tool call
with the tolerant parser as the fallback). `DOJO_AI_BACKEND` / `DOJO_PROVIDER` picks
one (`mock` for offline), `DOJO_MODEL` overrides the model, `DOJO_MODEL_<ROLE>`
overrides it per role, `DOJO_TIMEOUT` overrides the per-role bounds. Keys come from
each provider's env var (or its `DOJO_`-prefixed alias) and then the gitignored
dotenv; `dojo setup` detects any provider's key, writes `DOJO_PROVIDER`, and
`--provider X` pins the choice. **Never log or prompt-embed a key.**

Roles today: `tutor`, `discussion`, `teacher`, `reviewer`, `auditor` (leak check).
The evidence model adds at most a review auditor (phase 15, `docs/grading.md`); a
curriculum may not add roles, and the authoring roles that used to live here
(`curator`, `curation_auditor`, `referencer`) left with the authoring tooling
(rule 13). Every
call names its role — `backend.chat_json(Role.TUTOR, …)` — and the role decides the
system prompt's address, the token budget, the temperature, the timeout, the
provenance record, and (for `MockBackend`) which canned answer comes back.

## 7. Configuration and state layout

- `config.CONTENT_DIR` — content that ships with the engine: `curriculum-kit/` (the
  example curriculum, templates, the prompts). Read-only at runtime.
- `config.DATA_DIR` (`DOJO_DATA_DIR`) — **user state**: `dojo.db`, `logs/`,
  `dojo.conf`, `curation/`. This is what `tests/conftest.py` redirects; a full run
  must leave the real directory byte-identical.
- `config.CURRICULA_DIR` (`DOJO_CURRICULA_DIR`, default
  `~/.local/share/dojo/curricula/`) — **user content**: one directory per installed
  curriculum, each with a `.dojo-source.json` recording where it came from and at
  which commit. Moving it must never move the DB, and vice versa.
- `config.WORKBENCH_DIR` (`DOJO_WORKBENCH_DIR`) — the editor/debugger workspace,
  outside the repo.

**Read paths at module scope** (`from dojo.config import WORKBENCH_DIR`); an
in-function import re-reads the module attribute and silently escapes every
monkeypatch. Product-level tests drive `cli.main` behind the `cli_env` fixture, and
`FakeConsole` **raises** when a script runs out of answers rather than silently
answering "quit".

## 8. Engine conventions worth knowing before you touch them

- **Judge protocol.** `judge/runner.py` writes the artifact, the cases and a harness
  into a temp dir and executes it with a timeout. A case is `{"args": …, "expected":
  …}` plus optional verdict tags (`compare: sorted`, `compare: approx:1e-4`,
  `rounded:n`, `predicate`), or an `ops` sequence for stateful class problems.
  Default is strict JSON equality with sorted keys. The harness swaps `sys.stdout`
  *and* file descriptor 1, reads the last parseable line, bounds both streams and
  kills the whole process group on timeout; `run_cases` never raises and refuses an
  empty case list. A case that raised is `status="error"`, not `wrong_answer`.
  `run_cases(..., python=…)` is the interpreter seam a curriculum uses for its own
  environment.
- **Measurement.** One measurement per subprocess, medians across repeats, an
  untimed warm-up, the timed call with **no tracer running**, then the space call
  with tracemalloc active and untimed; arguments are deep-copied per call. The
  verdict is a *ratio trend against a paired reference*, never an absolute fit, and
  "unresolved" is a legitimate answer. A curriculum declares *what* to measure; the
  framework decides how the verdict is reached and how uncertainty is stated.
- **Evidence and scheduling.** An attempt row exists iff the student submitted;
  `quit` records nothing. Cards are per `(user, curriculum, item)` and are derived
  state: `rebuild_item_cards` replays the attempt log and is the repair path, which
  is also how the migration proves itself. Grades are 1–4 and persisted on the
  attempt; the FSRS equations are the published ones with default weights and are
  not re-tuned by hand. Weak evidence seeds conservatively and is disclosed
  (`docs/retention.md`).
- **Session.** `run_day` is one loop with a persisted phase (`solving` |
  `post_solve`); `polish` is a mode switch, not a re-grade; a solving-mode command
  typed post-solve gets a pointer line rather than being sent to the model. Every
  session writes a fresh artifact template; a session killed before submitting
  leaves state behind and the next invocation resumes it, so `load_state` stays
  tolerant of unknown keys.
- **Workbench.** The artifact is written outside the repo, starts with a shebang
  pointing at dojo's venv (or the interpreter the curriculum declares), carries a
  fenced `if __name__ == "__main__"` examples block, and is rendered *by the
  curriculum* through `session/workbench.py`. Every AI reader and the static layer
  consume `student_view` — dojo's chrome stripped, the student's edits preserved.
- **Terminal.** Prompts go through `terminal.make_prompt` (prompt_toolkit on a TTY,
  `console.input` otherwise), AI prose renders through `render.render_ai`, and
  numbered choices go through one shared picker — the same one enrollment uses.
  Keep hints to one line.
- **CLI.** Each subcommand returns an exit code. `main` catches `KeyboardInterrupt`
  (130) and `EOFError` (1) and leaves the state file for a resume. Bare `dojo` runs
  the daily routine; a first non-flag argument is an item id. Never use argparse's
  `help=SUPPRESS` (Python 3.13 prints `==SUPPRESS==`). Power tools stay dispatchable
  and out of the guide, each documenting itself via `--help`.
- **Debug log.** Every live AI exchange is appended to gitignored
  `data/logs/dojo.log` (JSONL, the raw response *before* parsing). Only live
  backends write it. The phase component of the version gates retention, so
  finishing a phase clears the log while the commits inside a phase accumulate.

## 9. Definition of done

- `uv run pytest` passes, offline, and new behaviour has tests that fail before the
  change.
- The never-solve boundary is unchanged, or narrowed deliberately with the rationale
  written down and pinned by a test.
- User-visible changes update `README.md` and the matching `docs/` file; phase work
  lands in `roadmap/`.
- The branch check in §0 was actually run before the commit.
