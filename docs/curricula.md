# Curricula — the format, the loader, and what the engine does with it

A curriculum is a local, versioned bundle of practice. This document is the
contract between a curriculum and the engine; it is the seam the whole rebuild
hangs on.

**Format version 1 — explicitly unstable.** It is frozen when two real curricula
(NeetCode 150 and JAX) use it, not before. Until then, changes are expected and a
manifest's `format` field records which revision it was written against.

## 1. The three questions

When you are unsure where something belongs:

- Does it only make sense for one body of content? → **the curriculum's repository**.
- Is it a *policy* — which topic is next, what to measure, what "pass" means, what a
  warm-up is? → **declared in the manifest**, implemented by the curriculum.
- Is it a *mechanism* — isolation, scheduling math, evidence storage, prompting,
  display? → **the engine**.

The engine knows the words *curriculum, topic, item, attempt, evidence, card*. A
curriculum supplies the words the student sees.

## 2. Directory layout

```
my-curriculum/
  curriculum.toml          # everything declared (below)
  items/<item>.md          # the statement the student reads
  items/<item>.py          # the artifact they open and submit (the template)
  checks/<item>.py         # visible checks — the student can run these; dojo puts
                           #   them in the workbench's examples block
  assessment/<item>.py     # QUARANTINED: oracle, generated cases, reference,
                           #   rubric, measurement policy
  measure/<item>.py        # optional measurement policy (may live in assessment/)
  README.md                # how to use it, what it claims, what it does not
  .dojo-source.json        # written at install time: URL, commit, installed-at
```

Only `curriculum.toml` is required. Everything else is referenced from it, and a
reference that does not resolve is a validation failure, not a silent skip.

### Two namespaces, and the never-solve guarantee

The loader exposes a curriculum through **two** namespaces, and that split is the
reason references and oracles can live in a curriculum at all:

| namespace | contains | who may touch it |
|---|---|---|
| `catalog` | topics, items, statements, artifact templates, visible checks, display vocabulary, measurement *plan* (sizes and axis, never the numbers) | the session, the workbench, the CLI, the student |
| `assessment` | oracles, generated cases, references, rubrics, hidden checkers, the measurement implementation | the judge and measurement subprocesses only |

`assessment` is loaded lazily, never imported by the engine at module scope, and
never reachable from a prompt builder. The tutor's context is assembled from a fixed
field list — statement, the student's code as `student_view` renders it, the current
tier, the hint history — and `tests/test_never_solve.py` asserts the boundary as an
**import graph per installed curriculum**: if anything on the tutor path can reach an
assessment module, the suite fails. The v0.8 teacher narrowing (topic + conversation
only, topic-canonical code allowed) is unchanged and still pinned by its own test.

## 3. `curriculum.toml`

```toml
[curriculum]
id = "jax"                       # [a-z][a-z0-9-]*; the card and row namespace
title = "JAX for researchers"
version = "0.3.1"                # the curriculum's own version (semver)
format = 1                       # the manifest format revision it was written for
dojo = ">=1.14,<2"               # engine compatibility
language = "python"
interpreter = "curriculum"       # dojo-venv | curriculum | system
dependencies = ["jax[cpu]>=0.4"] # installed by `dojo curriculum setup`, with consent
source = "https://docs.jax.dev/" # where the material comes from (provenance)
license = "private"              # SPDX id, or "private" = never publish this

[display]                        # the words the student sees; the engine's defaults
topic = "Module"                 #   are Topic / Item / Outline
item = "Lab"
outline = "Path"
difficulty = ["intro", "core", "advanced"]

[warmup]
policy = "re-solve"              # re-solve | re-derive | re-justify
budget = 2                       # how many `dojo day` drains by default

[[topic]]
id = "tracing"
title = "JIT and tracing"
prereqs = []                     # topic ids; a graph, not a chain
summary = "What a trace is, and why the first call is different."

[[item]]
id = "trace_a_random_walk"
topic = "tracing"
title = "Trace a random walk"
difficulty = "intro"             # from [display].difficulty
statement = "items/trace_a_random_walk.md"
artifact = "items/trace_a_random_walk.py"
evidence = "executable"          # executable | measured | judged | self-reported
external_id = "jax-docs/tracing/random-walk"   # optional, unique in this curriculum
checks = "checks/trace_a_random_walk.py"
assessment = "assessment/trace_a_random_walk.py"
# no separate measurement key: the assessment module registers @measure too
tags = ["jit", "pytree"]

[aliases]                        # renames, so history survives a curator's tidying
topics = { "jit" = "tracing" }
items = { "trace_fn" = "trace_a_random_walk" }
```

**Required:** `[curriculum]` (id, title, version, format, dojo, language), at least
one `[[topic]]` and one `[[item]]`. Everything else has a documented default.

### `evidence` — what an item can establish

| value | meaning | the engine expects |
|---|---|---|
| `executable` | the work is correct | `assessment` registering an `oracle` + `cases`, or `checks` that are a complete verdict |
| `measured` | how it scales or behaves | the above **and** `measure` (a policy; see §5) |
| `judged` | how good it is | `assessment` registering a `rubric`; the reviewer judges, and a gating judgment needs an audit pass |
| `self-reported` | what the student says | nothing executable; the session asks, and the answer is labelled as a claim |

An item that declares `executable` and provides only visible checks is a validation
error — "the student can run it" is not "dojo can verify it". An item that declares
`judged` is honest about not being machine-checkable, and that is a legitimate
choice: the label is displayed, and the schedule treats the grade as self-reported
evidence (`docs/retention.md`).

## 4. The assessment module

Assessment code is ordinary Python that registers what it provides, using the same
decorator style the engine has always used:

```python
# assessment/trace_a_random_walk.py  — QUARANTINED
from dojo.curriculum.registry import cases, checker, measure, oracle, reference, rubric

@oracle("trace_a_random_walk")          # the correctness anchor (may be brute force)
def _oracle(steps, seed): ...

@cases("trace_a_random_walk")           # (n, rng) -> (args, expected) or (args, expected, extras)
def _cases(n, rng): ...                 #   extras may carry the verdict tags below

@reference("trace_a_random_walk")       # the canonical solution the student is paired against
def _reference(steps, seed): ...

@rubric("trace_a_random_walk")          # only for judged items
def _rubric(): return {"dimensions": [...], "pass": "..."}

@measure("trace_a_random_walk")         # only for measured items; returns a plan
def _measure(ctx): return {"axis": "steps", "sizes": [64, 256, 1024], "baseline": "reference"}
```

Rules the loader enforces:

- A registration name must match the referencing item's id; an unregistered
  reference is a validation failure.
- Verdict tags are the engine's existing vocabulary (`compare: sorted`,
  `compare: approx:1e-4`, `rounded:n`, `predicate: <checker>`), so a curriculum
  cannot invent a comparison the judge does not implement.
- The module runs in a bounded subprocess under `proc.run_capped` with child limits
  — a curriculum cannot hang, fork-bomb or OOM the engine.
- Imports of anything outside the standard library, its declared dependencies and
  `dojo.curriculum.registry` are refused at load time.

## 5. Measurement policies

The engine owns the *method*: one measurement per subprocess, medians across
repeats, an untimed warm-up, the timed call with no tracer running, arguments
deep-copied per call, and a verdict that is a **ratio trend against a paired
reference** with an explicit "unresolved". It never fits an absolute curve (v0.11
tried; the honest output was a bracket nobody could use).

A curriculum owns the *policy*:

```python
{"axis": "n",                  # the variable the ladder climbs — shapes, batch sizes,
                               #   steps, rows; whatever the subject scales along
 "sizes": [...],               # the ladder
 "baseline": "reference",      # or "naive" — a deliberately un-optimized but correct
                               #   implementation, which is what makes a JAX claim
                               #   meaningful ("jitted vs the same loop in Python")
 "stats": ["time"],            # extra statistics the interpeter collects —
                               #   JAX will add "compile", "step", "device_memory"
 "compare": "strict"}          # how outputs are checked while measuring
```

An item with no `measure` is reported as **not measured**, in those words. An item
whose policy returns `{"axis": None}` is reported as **not measurable here** — the
honest answer for anything whose cost does not vary with a scalar, and better than a
column of dashes that implies someone forgot.

## 6. Warm-up policy

A card is a memory of an *item*, and what "recall" means depends on the subject:

| policy | the warm-up is | fits |
|---|---|---|
| `re-solve` | a blank template for the same item, solved again from scratch | problems, exercises |
| `re-derive` | the same item with fresh inputs, or a statement-only variant the curriculum generates | anything where the *method* matters more than the instance |
| `re-justify` | a short written justification, judged against the rubric | design and taste: "why this chart?", "why this sharding?" |

The curriculum declares the policy; the session, the grading, the grade prompt and
the card update belong to the engine. `budget` is the default number of warm-ups
`dojo day` drains; the student can always drain more (`dojo warmup --limit N`), and
the session always says how many cards remain due.

## 7. Identity, versions and renames

- An item's identity is **`(curriculum.id, item.id)`**. Two curricula may both have
  an item called `stack`; they are different memories, and they never share a card.
- `external_id` is optional and, when present, **unique inside its curriculum** — a
  partial unique index enforces it. It exists so a curriculum can point at the
  outside world (a LeetCode number, a documentation anchor) without making that
  outside identity the key: the live bank learned this the hard way, carrying four
  problems twice because the curated row and the fetched row disagreed about names.
- **Renames are declared, never implied.** `[aliases]` maps an old id to its new
  one, and the loader applies it when reading history. A manifest that *drops* a
  topic or item that has attempts or cards fails validation unless the drop is
  recorded as an explicit `retired = true` on that entry — history stays
  addressable, and nothing a student earned disappears because a curator tidied up.
- A curriculum's `version` is its own; the engine records which version and commit
  produced each row (`attempts.curriculum_version`), so a score trend can be read
  against the content that produced it.

## 8. Validation — what the loader refuses

Fail loudly, never half-work:

- `id`, `version`, `format`, `dojo` missing or malformed; an unsupported `format`.
- A `dojo` range that excludes the running engine (with the numbers in the message).
- A topic graph with a cycle, a prereq naming a missing topic, or two topics with
  the same id.
- An item referencing a missing topic, an item id that is not
  `[a-z][a-z0-9_]*`, or a duplicate id; two items sharing an `external_id`.
- A file reference that does not resolve, or an artifact that does not compile.
- `evidence = "executable"` with no oracle/cases registration; `evidence =
  "judged"` with no rubric; a registered name with no referencing item.
- An `assessment` module importing anything outside its allowances, or a manifest
  key the engine does not know.
- A dropped topic/item with history and no `retired = true`.

The **loader** runs all of it and prints every problem, not the first: enrolling a
curriculum is the validation, so there is no separate `validate` command to forget to
run. A curriculum the loader refuses is not servable, and the message names the file
and the line (see §9).

## 9. Enrollment and installation

```bash
dojo enroll github.com/<you>/dojo-curriculum-jax   # clone into CURRICULA_DIR, validate, import, enroll
dojo enroll ./my-curriculum                        # a local working copy (symlinked, not copied)
dojo curricula                                     # installed + enrolled, versions, health
dojo unenroll jax                                  # pause; history and cards stay
```

That is the engine's whole curriculum surface. There is no `new`, `validate`,
`update` or `run`: **enrolling is validating**, re-enrolling the same source is how a
curriculum is updated, and a curriculum's own maintenance scripts live in its
repository and run there. The engine does not create curricula — see §10.

Installed curricula live in `config.CURRICULA_DIR`
(`~/.local/share/dojo/curricula/<id>/` by default), each with a `.dojo-source.json`
recording the URL, the commit and the install time. Installing is a filesystem
operation plus a validation; **enrolling** is a row in `enrollments` for the active
user. Un-enrolling is reversible and touches no history.

The engine ships exactly one curriculum — the fixture under
`tests/fixtures/curriculum-demo/` — which is the format's executable specification,
the loader's test double, and the skeleton a new curriculum starts from (copy it).
A fresh install with nothing enrolled says so and names the one command that changes
it.

## 10. Authoring is third-party

**The engine does not author curricula.** It provides the specification, enrolls what
you built, and runs it — deliberately, because content tooling ages at a different
rate than the engine, and because a curriculum someone else wrote must be auditable
rather than modifiable in place.

Third parties get, in this repository:

- this specification (the normative contract the loader enforces);
- `curriculum-kit/example/` — a complete, tiny curriculum in the format;
- `curriculum-kit/AGENTS.template.md` — the conventions a curriculum repository
  should start from;
- `curriculum-kit/prompts/` — prompts for an AI agent that plans a curriculum from a
  source, authors an item, audits a curriculum, or ports an existing corpus.

The fourth claim in dojo's definition — *AI curriculum generation* — lives out there
with them: it is a use of those prompts, not a feature of the engine. The engine's
only obligations toward it are that the specification be honest, that the gates be
enforceable, and that `dojo report` be able to audit what a generator produced.

Authoring by hand is the reference path: copy the example, write the manifest and the
items, register the oracle/cases/reference (and a rubric or a measurement policy where
the evidence kind calls for one), then `dojo enroll .` — which validates everything
and refuses the whole curriculum if anything dangles.
