# Evidence — what dojo knows about what you did

dojo's second claim is that **evidence moves the schedule, and only evidence**.
That requires two things the engine takes seriously: evidence has a *kind* with a
*kind-specific strength*, and the display never upgrades one kind into another. This
document is the specification for both, and for the honesty rules that constrain
every agent that produces evidence.

Nothing here is curriculum-specific. A curriculum declares which kinds its items can
produce ([curricula.md](curricula.md) §3); the engine decides what those kinds mean.

## 1. The four kinds

| kind | what it establishes | produced by | its failure mode | strength |
|---|---|---|---|---|
| **executable** | the work is correct: it runs, and its output matches an oracle it never saw | the judge harness, in an isolated subprocess | a wrong oracle, or cases that do not respect the statement | **verified** |
| **measured** | how the work scales, stated relative to a paired reference | the measurement framework + a curriculum's policy | measuring the wrong axis, or a contaminated reading | **measured** |
| **judged** | how good the work is: approach, idiom, naming, reasoning | the reviewer against the curriculum's rubric | a model that is wrong, unreadable, or unavailable | **advisory** (audited: still advisory, better founded) |
| **self-reported** | what the student says: claimed complexity, recall grade | the session's prompts | optimism, or a misunderstanding of the claim | **claim** |

A fifth kind, `peer`, is contemplated and not built: two students grading each
other's design work is a legitimate evidence source for judged subjects, and it is
out of scope until someone enrols in a curriculum that needs it.

The engine's rule for combining them: **the strength of a conclusion is the strength
of the weakest evidence it rests on.** A solve that passed its cases and whose review
praised the approach is *verified*; a re-architecture praised only by the reviewer is
*judged*; a growth claim whose measurement came back `unresolved` rests on the
student's own claim, and says so.

## 2. The record

Every piece lands in `evidence(attempt_id, revision, kind, source, strength,
verifier, payload, unresolved, produced_at)` — one row per piece, queryable, so the
disclosure is a fact about the database rather than a rendering choice. Alongside it:

- `attempts.ai_provenance` — which backend and model produced the attempt's
  AI-derived fields, so a mock row can never be mistaken for a live one.
- `attempts.curriculum_version` — which content version produced it, so a trend can
  be read against the item as it was.
- `attempts.recall_grade` — the persisted 1–4 grade; the card aggregates alone cannot
  reconstruct a recall curve.
- Revisions carry the artifacts *that* version produced, so polishing never rewrites
  history.

## 3. Gates and advisories

The distinction is the whole reason the tiers exist:

- **An advisory** shapes what the student reads. The reviewer's rubric, the static
  findings, a measurement note: none of these can fail a submission, and none of them
  are facts.
- **A gate** decides something: it marks a unit complete, or it lets an interval grow
  past what a self-report alone would justify. A judgment that gates requires an
  **independent audit pass** — a second call, different prompt, checking the first
  against the rubric — and the audit's disagreement is recorded as `unresolved`, not
  smoothed into a pass. The precedent is already in the engine: the leak audit runs
  on every hint and fails closed, and the curator's dual-oracle differential refuses
  a proposal whose two oracles disagree.

Two further rules follow from "an AI outage must never cost a session":

- When a judgment cannot run — no network, no key, an unreadable reply — the work is
  recorded as **submitted, unjudged**. It is scheduled from the self-report, the
  display says `unjudged`, and the student can ask for judgment again later
  (`report` / a re-review). Nothing is blocked, and nothing is faked.
- A gating judgment that fails its audit does not become a failure grade; it becomes
  *unresolved*, which the display shows and the scheduler treats as weak evidence.

Cost discipline: audits are for gates. An advisory review is not audited, because
paying for a second opinion on prose nobody's schedule depends on is how trust gets
expensive by accident.

## 4. Executable evidence

`judge/runner.py` writes the artifact, the cases and a harness into a temp dir and
executes it with a timeout. One of four statuses comes back, and they mean different
things:

| status | meaning |
|---|---|
| `correct` | every case passed |
| `wrong_answer` | every case *ran*; at least one value disagreed |
| `error` | at least one case raised, or the harness could not run — a crash is not a wrong answer, and the two need different coaching |
| `timed_out` | the wall clock expired; per-case results are unavailable |

An **empty case list is refused** (`status="error"`, label `no cases`): `all_passed`
is true for zero cases, so an unverified item used to be a free solve. An item counts
as executable only when it registers an oracle and a generator (or its visible checks
are a complete verdict) — a curriculum that claims `executable` without one is a
validation failure, not a silently weaker item.

Verdict tags are the engine's vocabulary, so a curriculum cannot invent a comparison
the judge does not implement: `compare: sorted` (deep-sorted equality for any-order
outputs), `compare: approx:1e-4` and `rounded:n` (float tolerance), `predicate: name`
(a checker validating `(module, got, args)`), and `ops: […]` for stateful class APIs.
Default is strict JSON equality with sorted keys — `1.0` and `1` differ, deliberately,
because "approximately right" is a verdict the case must ask for.

**Oracle and reference are different artifacts with different jobs.** An *oracle* is
the brute-force correctness anchor: deliberately simple, because an obvious
implementation is one you can trust; it is not a performance baseline (it *is* the
slow thing) and it cannot run at scale. A *reference* is the canonical,
intended-complexity solution the measurement pairs against, and it is admitted only
when it agrees with the oracle everywhere the oracle can run — a wrong baseline would
produce confident verdicts about the student from a broken yardstick. In a curriculum
both live under `assessment/`, quarantined from every agent.

Containment is the parent's job (`dojo/proc.py`): output goes to temp files and is
read back capped (a print loop once reached ~1.9 GB in three seconds); the child runs
in its own session and its whole process group is killed on timeout (a spawned
grandchild once outlived a `timed_out` run); the harness sets address-space, file-size
and CPU limits on itself; the result is read as the last parseable line, so a late
print cannot corrupt the protocol. A curriculum's own evaluators run through the same
boundary, which is what makes external assessment code acceptable at all.

## 5. Measured evidence

Method (engine): one measurement per subprocess, medians across repeats, an untimed
warm-up, the timed call with **no tracer running**, then the space call with
tracemalloc active and untimed; a fresh deepcopy of the arguments per call, so an
in-place `sort()` cannot change what later calls do. Never tracemalloc inside the
timed region — its per-allocation bookkeeping is superlinear, which is exactly what
once made allocation-heavy `O(n)` code read as `O(n log n)`.

Verdict (engine): the student and the reference are measured interleaved at each
size, and the ratio trend becomes a class *relative to the reference* or an explicit
**`unresolved`**. Three outcomes are legitimate and one is forbidden: agreeing with
the claim, disagreeing by one class, and "the evidence does not support a reading".
The forbidden one is claiming a class the ratio cannot support — and the forbidden
mechanism is an **absolute curve fit** (v0.11's `fit.py`): it cannot separate `O(n)`
from `O(n log n)` at feasible sizes, and its honest output was a bracket nobody could
use.

Policy (curriculum): the axis, the ladder, the baseline (a canonical reference, or a
deliberately naive one — which is what makes "jitted versus the same loop in Python"
a meaningful claim), extra statistics, and the output-comparison mode. An item with
no policy reads *not measured*; a policy that declines reads *not measurable here*.
Both are answers; neither is a zero.

The reviewer receives the verdict **and its strength**, with the instruction that an
unresolved measurement is not evidence against the student's claim. It used to be
handed a bare class and left to guess — and in the live data it consistently defended
students against the tool's own contaminated readings, which meant the AI layer was
silently error-correcting the deterministic one. Making the measurement honest was
the fix; telling the reviewer is the belt and braces.

## 6. Judged evidence

The reviewer returns a rubric-scored JSON object: correctness, approach quality,
style/idiom, naming, edge cases, complexity-claim check, complexity *reasoning* (is
the *why* sound?), reflection feedback, broader picture, overall comment. Inputs: the
statement, the submitted work, the raw self-reported claims (so the reasoning is
visible, not just the parsed class), the measurement and its strength, the static
findings, and the student's reflection — which is why reflection happens *before* the
review.

Hard rules: it critiques, never repairs — no alternative solutions, no code. Output
is schema-normalized before display and storage (dimensions may arrive as
`{"score", "comment"}` or as bare numbers; a real solve once returned bare ints and
the chart came out empty), scores are clamped to 1–5 (a 10-point model once shipped
9/5), and a transient non-JSON response gets one retry before the review is skipped.

For a curriculum whose items declare `judged`, the rubric comes from its
`assessment/`, and the reviewer's output is the item's primary quality evidence —
still advisory, still labelled, and audited when it gates (§3).

## 7. Self-reported evidence

Claimed time and space complexity, and the warm-up recall grade, are the student's
own reports. They are not a weakness to be apologized for: the recall grade is the
*only* input FSRS can use (nobody can measure your memory from outside), and the
complexity claim is itself a skill — the reviewer grades its reasoning, and the
measurement either agrees, disagrees, or declines.

What the engine must never do is *launder* them: a claim is stored as a claim, the
display distinguishes "claimed" from "measured", and weak evidence seeds an interval
conservatively ([retention.md](retention.md) §3) rather than inheriting the
confidence of a verified solve.

## 8. The display

- **The complexity table** compares three columns on two axes — the item's own
  target, the measured verdict, and the student's claim. A cell participating in a
  *disagreement* is red; a fully agreeing axis is green; an **unresolved measurement
  never reddens a claim** (it is not evidence), and an axis whose sides are
  incomparable is named in a dim note rather than left silent. Cells are literal
  text, never markup-parsed, so a raw user string cannot smuggle styling.
- **`dojo history`** prints expected / measured / submitted per attempt, oldest
  first, with the measured cell carrying the class *the differential derived* (or
  `no reference`, or `unresolved`).
- **`dojo progress`** aggregates reviewer scores per topic with recency-linear
  weighting and shows the card schedule — with each card's evidence kind, so a
  schedule built on self-reports says so.
- Where a curriculum declines to measure, the display says *not measurable here* and
  gives the reason, instead of showing an empty column that reads as an omission.

## 9. Reporting a problem with the grading

The audit loop is how the student can doubt the tool. `dojo report <item>` (and
in-session `report <your words>`) audits an **item's assessment**: a fresh oracle
pass cross-checked against the installed one, then an audit agent hunting
contract violations between the statement and the checks — ties graded by equality,
"unique answer" promises the generator does not enforce, constraint fidelity,
verdict-tag mismatches. `dojo report --curriculum <id>` widens it to the curriculum:
outline coverage, prereq sanity, gate results, provenance of every item. Findings
land in gitignored `data/curation/` and print; `--fix` re-authors through the
pipeline with rollback when the verdict is `fix`.

The student's words travel into the audit prompt under "WHAT THE STUDENT REPORTED",
are recorded as `student_note`, and the auditor must address the claim by name —
including telling the student it is wrong, because a report is evidence, not a
verdict. Automated cross-check findings always print alongside, so "no contract
violations" and "the cross-check never ran" can never be confused.

A report can never cost a session: it runs behind `guard`, and whatever fails inside
it prints one line and leaves the loop running. The rule underneath is that
model-written code is executed as *shape variance, never a fatal* — and the same
stance applies to a curriculum's assessment code, which is why it runs in the bounded
subprocess and not in the engine's process.

## 10. The honesty contract, in one place

1. Never claim what the evidence does not support; name the strength instead.
2. `unresolved`, `unjudged`, `not measured` and `not measurable here` are outcomes,
   not failures, and never redden a claim.
3. Never fit an absolute curve; a paired ratio or nothing.
4. A judgment never becomes a fact by assertion: gates need audits, and disagreement
   is recorded.
5. An unanswered AI never blocks the loop, and never silently counts as a pass.
6. Weak evidence schedules conservatively and is disclosed, on the row and on screen.
7. The tool's own failures are reported as the tool's, never as the student's.
