# history — phases 1–13, condensed

The full stage records for these phases are on `main` (`roadmap/v0.1.md` …
`roadmap/v0.13.md`, tagged through `v0.13.0`). This branch retired them because they
describe the pre-split design — one repository where the engine and the NeetCode 150
were the same thing — and keeping them here would invite cargo-culting a shape this
phase exists to remove. What follows is what the rebuild must preserve, phase by
phase, with the *why* that is still load-bearing.

| phase | what it delivered | what still matters here |
|---|---|---|
| v0.1 | the never-solve tutor and an empirical grader; the daily loop | the product's defining constraint, and the reason a tutor prompt is built from a fixed field list |
| v0.2 | the retention engine (spaced repetition over practice) | cards are derived state; FSRS is the model |
| v0.3 | the updating bank (fetch, land, upsert) | the bank mirrors content in **both** directions: seeds are additive, and a row nothing points at is pruned — loudly |
| v0.4 | deeper grading: static analysis, hints, reviews | advisory evidence never becomes a verdict |
| v0.5 | setup wizard, single-user ergonomics, bare `dojo` | one command a day, no decision fatigue; one computer, one user |
| v0.6 | tutor modes (ladder vs discussion) and the post-solve loop | the tier ladder, and that a discussion question is not a hint |
| v0.7 | the trust fix and terminal ergonomics; `report` | the audit loop: the student can doubt the tool, and the tool answers |
| v0.8 | learning mode (the teacher) | the one documented narrowing of never-solve; topic + conversation only |
| v0.9 | onboarding: minimal help, key detection, the wizard | the help surface is hand-written, and power tools stay out of the guide |
| v0.10 | progression: groups, ladders, a prereq gate | progression is a **policy** — this phase moves it into the curriculum |
| v0.11 | the correctness stage: attempt lifecycle, warm-up semantics, FSRS-4.5 with published equations | an attempt exists iff the student submitted; grades are persisted; a quit records nothing |
| v0.12 | the measurement stage: paired measurement against a reference, three-valued verdicts | a ratio, never an absolute fit; `unresolved` is an answer |
| v0.13 | session continuity, the workbench views, providers and roles | one loop with phases, `student_view` for every AI reader, role-keyed routing |

**Follow-ups that landed after `v0.13.0`** (also on `main`): per-item warm-up cards
migrated by replaying the attempt log; honest warm-up reporting (`due_phrase`);
duplicate-bank removal with a two-way prune; the report crash fixed and the branch's
`report <note>` added; one version source of truth; and offline behaviour — network
failures reported as the network, with bounded per-role timeouts.

Two lessons from that history are load-bearing for this phase, and are why several
rules in `AGENTS.md` read the way they do:

- **Identity carried by a filename drifts.** Eighteen problems existed twice because
  a fetched slug and a corpus slug disagreed; a year later four more were found the
  same way, untagged, with the roadmap's curated/missing flag decided by
  dict-iteration order. Hence `(curriculum, external_id)` uniqueness as a schema
  invariant, and renames as declared aliases.
- **A measurement that is wrong is worse than no measurement.** The v0.11 profiler
  reported classes from a fitted curve and was confidently wrong; the AI reviewer
  spent months quietly defending students against it. Hence the ratio rule, the
  explicit `unresolved`, and the rule that evidence carries its strength — which is
  what phase 15 makes behavioural.
