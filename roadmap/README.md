# roadmap

The plan of record for the branch `curricula` — see `HANDOFF.md` in the
repository root if you are picking this work up cold. One file per phase; a phase is done when its
definition of done is met, the version is bumped and the commit is tagged
(`docs/development.md` §7).

| file | what it is |
|---|---|
| [`v0.14.md`](v0.14.md) | **in flight** — the curricula rebuild: the engine/curriculum split, NeetCode 150 moving out, enrollment, the migration |
| [`next.md`](next.md) | the backlog: phase 15 (the evidence model, then JAX), phase 16 (AI curriculum generation), and everything deliberately parked |
| [`history.md`](history.md) | the delivered phases, condensed. The full records are on `main` — this branch retired them because they describe the pre-split design |

## The arc

- **Phase 14 — the split.** dojo becomes an engine and NeetCode 150 becomes a
  curriculum in its own repository. No new subject, no new student-facing capability:
  the same daily loop, with the LeetCode shape removed from the engine. This is a
  breaking phase, and it is the reason the work happens on a branch while `main`
  keeps serving practice (`AGENTS.md` §0).
- **Phase 15 — evidence, then JAX.** The evidence tiers gain their behaviour
  (disclosure, gating audits, conservative seeding), and the first curriculum written
  against the new format arrives with its own measurement suite — the proof that the
  format generalizes beyond the shape it was extracted from.
- **Phase 16 — generation.** Bootstrapping a curriculum from a source you trust, the
  fourth claim in dojo's definition, which is only credible once a hand-authored
  second curriculum exists to compare it against.

## How a phase doc is written

Each one states: what the phase is for, what moves and what stays, the increments
with their definition of done, the acceptance tests that prove it, the risks with
their mitigations, the decisions taken (with dates), and what it deliberately does
not do. `v0.14.md` is the model to copy.

Decisions that shape future phases are recorded in the phase doc, not in chat — the
five decisions that define this rebuild are in `v0.14.md` §7, and the reasoning
behind them is in the discussion that produced them (summarised there).
