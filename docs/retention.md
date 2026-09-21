# Retention: the scheduler and warm-ups

## What a card is (v0.13 follow-up)

**One card per solved problem.** A warm-up re-solves that specific problem from a
blank template, and its grade updates that problem's stability and difficulty.

The unit used to be the *pattern*, and the live data shows why that failed:
`arrays_and_hashing` held one card reporting 34 days of stability while eight of
its ten solved problems had never been recalled once; `valid_parentheses` alone
earned 91 days, which the `stack` card diluted to 50. A single memory cannot
describe problems that decay at different rates, and the schedule it produced was
an average nobody had actually demonstrated.

`pattern` survives as the rollup key: `dojo progress` shows per-pattern counts,
mean stability and — the honest signal — the **weakest** card in the pattern,
while `dojo progress --problems` lists every card, coldest due first.

**Migration.** Existing pattern cards were replaced by a replay of the attempt
log: each solved problem's own state is reconstructed from its submit rows
(`kind`, `recall_grade`, `submitted_at`). Grades persisted before v0.11 were
folded into card aggregates and are gone — those eight recalls replay as "good",
the same assumption the old aggregates encoded. Problems that were solved but
never recalled are genuinely overdue (FSRS's initial stability is under a day), so
the rebuild *spreads* that backlog over a week: one card a day, driest first. That
is a capacity decision, not a memory claim, and `dojo rebuild-cards --spread N`
redoes it with a different window.

## FSRS-4.5

Each (user, pattern) card carries **stability S** (days to 90% recall) and
**difficulty D** (1–10), plus a due date. Recall probability follows the
power-law forgetting curve

    R(t, S) = (1 + FACTOR * t / S) ** DECAY

with FSRS's `FACTOR = 19/81` and `DECAY = -0.5` (so R ≈ 0.90 at t = S — the
default review interval equals the stability).

State updates are the published FSRS-4.5 equations with FSRS's **default
weights** (`FSRS_W` in `scheduler.py`), not tuned constants:

    S0(G) = w[G-1]                                          new card
    D0(G) = clamp(w4 - (G-3)*w5, 1, 10)                     new card
    S'    = S*(1 + e^w8 * (11-D) * S^-w9 * (e^((1-R)*w10) - 1))
            * hard_penalty * easy_bonus                     grade >= 2
    S'    = min(S, w11 * D^-w12 * ((S+1)^w13 - 1) * e^((1-R)*w14))   lapse
    D'    = clamp(w7*w4 + (1-w7)*(D - w6*(G-3)), 1, 10)

Initial stability by grade is 0.4 / 0.6 / 2.4 / 5.8 days for Again / Hard /
Good / Easy. A card answered *good* three times at its due dates reaches about
24 days. The previous hand-tuned constants reached 1.5 days after twelve
reviews while describing themselves as "FSRS-4.5 with rounded constants" —
the stability increment was roughly 20× smaller than the formula above, which
is why nothing ever left the same-day regime.

**One documented deviation:** intervals are capped at `MAX_INTERVAL_DAYS`
(365). FSRS permits multi-year intervals; a pattern being studied for
interviews has to come back inside the horizon it is being studied for.

**Known mismatch:** FSRS's weights are fitted to item-level, day-scale,
self-graded Anki reviews. dojo grades a *pattern* from a hint count, so the
model is applied to a coarser and noisier signal than it was trained on. The
published defaults are better provenance than invented constants — they are
simply not a claim that dojo's grades mean what Anki's do.

## What the scheduler decides

- **Due warm-ups:** cards with `due_at <= now`, most overdue first (`dojo day`
  runs up to 2, `dojo warmup` up to 3).
- **Which problem to warm up:** the *least recently practised* solved problem
  in the pattern — aggregated per problem (`MAX(submitted_at)`), so practising
  a problem pushes it to the back and consecutive warm-ups rotate. The earlier
  query ordered every correct attempt and took the first, which selected the
  problem solved earliest *ever*: a value that never ages, so one problem was
  served forever (`valid_parentheses` five times while four other solved
  problems in that pattern went untouched).
- **Which problem to solve next (v0.10):** the roadmap order — patterns are
  walked in progression order under the hard prereq gate, and within a pattern
  the earliest unsolved ladder problem wins (ladder problems are
  LeetCode-numbered; dojo's own problems are the fallback once the ladder is
  exhausted). Stability governs warm-up scheduling.
- **Backfill:** `dojo init` creates cards for every (user, pattern) with a
  solved attempt, due immediately.

## Grades

Grades follow the Anki convention: 1 = forgot, 2 = hard, 3 = good, 4 = easy.
The suggestion is a prior derived from the session's ladder hints, and it is
only a suggestion — type any grade to override it:

| ladder hints | suggested |
|---|---|
| 0 | 3 (good) |
| 1–2 | 2 (hard) |
| 3+ | 1 (forgot) |

Two details matter. Only `ladder`-kind hints count: a `discussion` question is
exploring, not struggling. And the suggestion tops out at **3**: a hint-free
re-solve is evidence *against* struggle, not evidence of ease, and FSRS's easy
bonus multiplies the whole grown stability by 2.61 — claiming "easy" should be
a deliberate choice rather than the default.

**Grades are persisted** (`attempts.recall_grade`). They used to be folded
into the card's aggregates and thrown away, which made per-pattern recall
curves — the analysis the whole model exists to enable — unreconstructible.

## Warm-up semantics

`run_warmups` forces a fresh template (re-solve from scratch), creates an
attempt with `kind='warmup'`, and skips reflection (the recall grade replaces
it). **Quitting a warm-up records nothing** — no attempt row and no card
change — because a deliberate quit means "not now", not evidence of
forgetting. A lapse is recorded only when you grade yourself 1. A pattern card
without a solved problem is deferred a day.

## Session lifecycle

**An attempt row exists if and only if the student submitted.** A session
creates its row on the first submit (pass or fail) and updates it thereafter;
quitting before any submit writes nothing at all. This is what makes `quit`
safe to use as "never mind" — it cannot pollute the learner model with a
phantom `unsolved` row, which is what an invocation that merely looked at a
problem used to leave behind. `status` therefore carries real information
(`correct` / `wrong_answer` / `error` / `timed_out`).

Workbench state (`workbench/<slug>.state.json`) is retired on submit and on
quit. Every new session starts from a blank template. A session killed before
submitting leaves its state file behind and the next invocation **resumes** it
— code and hints intact, the same attempt row — which is the only resume path
now that `quit` is a total abandonment. `dojo history` / `dojo show <id>`
recover anything from past sessions.
