# next — backlog

Phase 14 is in flight ([`v0.14.md`](v0.14.md)). What follows is what comes after it,
in the order it should, plus what is deliberately parked. Items that belong to a
*curriculum* rather than the engine (curating the remaining NeetCode ladder rungs,
the JAX content itself) live in that curriculum's repository and appear here only
where they constrain the engine.

## Phase 15 — evidence, then JAX

The evidence *model* lands in phase 14 (the record, the kinds, the strength field);
phase 15 makes it behavioural, then proves the format with a second curriculum.

**15.A — the evidence model, behavioural.**

- Tiers in the display: `dojo progress`, `dojo history` and the session summary say
  which kind of evidence a card or a class rests on, and `unverified` is a visible
  state rather than a blank.
- The gating rule: a judgment that marks a unit complete or lets an interval grow
  requires an independent audit pass (the `Role.AUDITOR` precedent — the leak audit
  and the curator's dual-oracle differential are the two existing examples). Audit
  disagreement is recorded as `unresolved`, never smoothed into a pass.
- Cost discipline: audits are for gates, never for advisory prose.
- "Submitted, unjudged": an unreachable reviewer records the work, schedules from the
  self-report, discloses the gap, and offers a re-review. An AI outage never blocks
  the loop and never counts as a pass.
- Conservative seeding for weak evidence, and the display that says so
  (`docs/retention.md` §3).
- A `dojo evidence <attempt-id>` view: every piece of evidence for one attempt, with
  its source and its strength. (The debugging tool for the next time a verdict looks
  wrong.)

**15.B — JAX, the first new curriculum.**

- Hand-authored items for the first unit (tracing/JIT semantics): the curator is
  unproven on transformation semantics, and the point of phase 15 is a curriculum
  someone *trusts*, not one generated quickly.
- **Its own measurement suite**, on the engine's framework: first-call compile time
  in its own region, steady-state step time after `block_until_ready()`, device
  memory or an explicit "not measurable on CPU", and a naive-but-correct baseline so
  "jitted versus the same loop in Python" is a paired claim rather than a bare number.
- Verdict vocabulary that says something pedagogical: `RETRACED`,
  `HOST_ROUNDTRIP`, `PYTHON_LOOP_IN_TRACE`.
- **Spike before API.** The mechanism for re-trace detection is unsettled (`jax.monitoring`
  counters vs lowered-HLO identity). Half a day of throwaway experiment decides it;
  no verdict ships whose mechanism is a heuristic dressed as a fact.
- The curriculum's own repository documents what it measures, what it does not, and
  what a warm-up means for it.

## Phase 16 — AI curriculum generation (third-party, kit-driven)

Generation happens **outside the engine** (AGENTS rule 13). What the engine owes it:

- a specification honest enough that a generator can target it, and a validator strict
  enough that a bad generation cannot install silently (`dojo enroll` is that gate);
- `curriculum-kit/prompts/plan-a-curriculum.md` and `port-a-corpus.md` — the workflow,
  written down;
- `dojo report --curriculum` as the audit a generated curriculum must survive;
- provenance that the format can *carry* per item (source, generator, gate results)
  even though the engine never writes it.

What a third-party generation project owns: ingest → outline → items → gates → the
curriculum-level audit → the candidate handed over for review. Coverage is reported as
*missing* where the outline skipped material, and every generated item's evidence kind
is whatever it can actually deliver.

A read-only spike is worth running during phase 15 — propose an outline from a JAX
documentation page with the kit's planning prompt and no format commitment — to learn
what the prompt needs.

## The authoring-tooling port (owner: the curriculum side)

The engine is losing its content tooling, and the NeetCode 150 corpus needs its
equivalents: the LeetCode intake (today's `fetcher/`), the item curator (today's
`curator/`, including the dual-oracle differential, the reference gate and the
shape-repair stance), `dojo reference`, and `dojo report --fix`. Until they exist on
the curriculum side, **curation continues on `main`**, where those commands still
work — which is why `main` stays a live product through this phase. Porting them is a
curriculum-side job built on `curriculum-kit/`; the engine's contribution is that its
judge, its measurement framework and its validator are usable from outside (`python
-c "from dojo.curriculum import validate"`), so the port does not reimplement them.

## Personalization (after generation exists)

- **Placement probes**: a curriculum declares, per topic, a few items whose verified
  outcome lets the outline skip what the student already knows. Skipped is recorded
  as skipped, never as completed.
- **Evidence-driven reordering**: topics whose cards keep lapsing are offered earlier.
- **Just-in-time items**: hitting an unknown concept offers `learn`, then generates
  the practice item that concept needs, gated like any other.
- **Curriculum tuning as a text edit**: the manifest is the personalization surface —
  difficulty ladder, warm-up policy, measurement axis, budgets — reviewed as a diff in
  the curriculum's own repository before re-enrolling it.

## Parked deliberately

- **Rust, and any multi-file artifact.** The crate case (a tree, a build pipeline, a
  diagnostics-shaped verdict, authored references because the curator cannot write
  Rust) is documented as a gap in `docs/architecture.md` §12 rather than built.
- **A compiled toolchain runner.** `run_cases(..., python=…)` covers an interpreter;
  a compiler's failure mode needs a different verdict vocabulary.
- **A public plugin API.** The format is v1-unstable until two curricula use it; a
  deprecation policy for a seam nobody has tested twice is premature.
- **Peer review as evidence.** Two students grading each other's design work is a
  real evidence source for judged subjects; it needs a second user model and is
  parked until someone enrols in a curriculum that wants it.
- **Fuzzing with shrinking** for the judge (still the strongest remaining correctness
  idea for executable items).
- **Reviewer calibration**: reviewer scores against subsequent warm-up grades, per
  topic — an audit loop for the *reviewer*, mirroring what `report` does for an
  item's assessment. Unblocked by persisted recall grades.
- **A TUI (Textual), a web UI, multi-machine sync.** The CLI loop is the product
  until it is not; nothing in this phase's design blocks any of them.
- **`problems.source` and other provenance gaps** from the v0.12 audit: a curriculum
  manifest now carries provenance natively, so the old column's job is done by
  design.

## Carried over from the v0.12 audit

[`docs/audit-v0.12.md`](../docs/audit-v0.12.md) remains the catalogue of engine-quality
findings, and it was written against the pre-split code. Its §4 coupling inventory is
what phase 14 acts on; its §6 ordering was consumed by phase 13. The findings that
survive the split unchanged — the judge's channel hygiene, the leak audit's
fail-closed behaviour, the measurement rules, the terminal fallbacks — are now pinned
by tests rather than by backlog items. Two are still open and land with phase 15:
reviewer calibration, and fuzzing with shrinking.
