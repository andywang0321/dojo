# AGENTS.md — working in a dojo curriculum repository

You are in a **curriculum** repository, not in dojo. dojo is the engine that will
enroll this repository and run it; the engine's own conventions live in
`github.com/<owner>/dojo` (`AGENTS.md`, `docs/curricula.md`). This file is the
starting point for the conventions that belong *here*.

Read, in order: this file, the engine's `docs/curricula.md` (the normative format),
and `curriculum-kit/example/` in the engine repo (the format by example).

---

## 1. What this repository is

A local, versioned bundle of practice, in the dojo curriculum format. It declares:

- **topics** — the learnable units, their order and their prerequisites;
- **items** — the things a student practises, each with an artifact and a statement;
- **evidence** — how a submission is checked, measured or judged, and therefore what
  a completed item actually proves;
- **measurement policy** — what to measure, on which axis, against which baseline;
- **warm-up policy** — what recall means here;
- **display vocabulary** — the words the student sees.

It is not an application. It has no CLI of its own beyond whatever your own `tools/`
scripts need, no database, and no knowledge of dojo's internals.

## 2. Hard rules

1. **`assessment/` is quarantined — and that is a promise, not a convention.** It
   holds oracles, references, hidden cases and rubrics: material no AI agent may ever
   see when tutoring a student. Never move assessment code into `items/` or
   `checks/`, never print it in an error message a student reads, and never reference
   it from a statement. The engine enforces this structurally; do not fight it.
2. **The evidence kind is a promise.** `executable` means an oracle *and* a generator
   exist and agree; `measured` means there is a policy that compares against a
   baseline; `judged` means an AI reads the work against a rubric; `self-reported`
   means the student's own word. Never declare a stronger kind than you can deliver —
   the student sees the label, and an inflated one is the worst thing a curriculum
   can ship.
3. **Gaps are reported, never filled by invention.** If the source material does not
   cover a topic, the outline says so. If a claim cannot be measured on a given
   machine, the policy declines (`axis = null`) rather than returning a number.
   "Not measurable here" is a respectable answer.
4. **Provenance per item.** Every item records where its material came from: a
   `source` URL or reference, and — for generated content — the model and the gate
   results. An item that cites a source that does not contain it is a bug.
5. **Identity is stable.** Item ids are `[a-z][a-z0-9_]*` and never reused for a
   different item. A rename is declared in `[aliases]`; a removal is declared with
   `retired = true`. A student's history is addressed by `(curriculum id, item id)`,
   and silently dropping an id with history breaks their schedule.
6. **Tests are offline and deterministic.** No network in tests. Never assert a
   performance class from wall-clock timing: assert mechanism (a re-trace count, a
   cache hit, a shape ladder) or coarse outcomes with generous bounds, and let the
   engine's paired ratio be the thing that claims a class.
7. **Copyright.** `license` in the manifest is accurate. Private or proprietary
   source material means a private repository, and `license = "private"` means never
   publish. Paraphrase rather than copy; cite what you paraphrase.
8. **Never commit a student's data.** Statements and checks only — no attempt logs,
   no workbench files, no debug logs, no API keys.

## 3. Layout

```
curriculum.toml
items/<item>.md            # statement
items/<item>.py|.md        # artifact template the student opens
checks/<item>.py           # visible checks (the student runs these)
assessment/<item>.py       # QUARANTINED
tests/                     # your gates, run before publishing
tools/                     # optional: your own authoring/maintenance scripts
README.md                  # what this curriculum claims and does not
```

## 4. Working here

- **Validate by enrolling.** `dojo enroll ./` installs a working copy, validates the
  manifest, imports the catalog, and refuses it loudly if anything dangles. There is
  no separate validate command: a curriculum that cannot be enrolled is not servable.
- **Iterate on a working copy.** `dojo enroll ./` symlinks rather than copies, so an
  edit plus a re-enroll is the loop.
- **Run your own gates before publishing.** At minimum: load every assessment module,
  generate cases at several sizes, and assert the oracle and the reference agree;
  assert every item's checks are consistent with its statement (the audit prompt is a
  good template); assert no two items share an `external_id`.
- **Measure before you claim.** If an item's `evidence` is `measured`, run the
  measurement locally at least once and record what it reported. If the policy cannot
  separate your item from the baseline, that is a finding: either pick a better axis
  or declare the item `judged`.

## 5. Reporting and auditing

`dojo report <item>` and `dojo report --curriculum <id>` audit what is installed and
accept the student's own words as evidence to check. They are read-only; a curriculum
is fixed by editing this repository and re-enrolling it. When a report finds a
contract violation, fix the statement or the case — never "fix" the verdict semantics
to make the finding go away.

## 6. Definition of done

- `dojo enroll ./` succeeds on a clean checkout of this repository.
- Every item's evidence kind is one it can actually deliver, and every `executable`
  item's reference agrees with its oracle on every visible check and generated case.
- Every item's checks respect its statement's constraints, and every "any order"
  promise is expressed with a verdict tag rather than hoped for.
- The README states what this curriculum measures, what it grades, what the tutor may
  say, and what is explicitly **not** claimed.
- Renames and retirements are declared; no id with history has been dropped.
- No student data, no keys, no assessment material outside `assessment/`.
