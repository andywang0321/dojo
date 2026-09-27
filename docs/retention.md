# Retention — FSRS, cards, and what a warm-up means

## 1. What a card is

**One card per solved item**, keyed by `(user, curriculum, item)`, with the topic as
the rollup key. A warm-up re-solves that specific item and its grade updates that
item's stability and difficulty.

The unit used to be the *topic* (then called a pattern), and the live data showed why
that fails: one card reported 34 days of stability while eight of its ten solved
problems had never been recalled once, and a well-recalled problem that had earned 91
days was diluted to 50 by its neighbours. A single memory cannot describe problems
that decay at different rates, and the schedule it produced was an average nobody had
demonstrated.

Two curricula may both contain an item called `stack`. They are different memories,
they never share a card, and un-enrolling a curriculum pauses your schedule for it
without touching what you learned.

`topic` survives as the rollup key: `dojo progress` shows per-topic counts, mean
stability, and — the honest signal — the **weakest** card, while `dojo progress
--items` lists every card, coldest due first.

## 2. FSRS-4.5

Each card carries **stability S** (days to 90% recall), **difficulty D** (1–10) and a
due date. Recall probability follows the power-law forgetting curve

    R(t, S) = (1 + FACTOR * t / S) ** DECAY

with FSRS's `FACTOR = 19/81` and `DECAY = -0.5`, so R ≈ 0.90 at t = S: the default
review interval *is* the stability.

State updates are the published FSRS-4.5 equations with FSRS's **default weights**
(`FSRS_W` in `scheduler.py`), not tuned constants:

    S0(G) = w[G-1]                                          new card
    D0(G) = clamp(w4 - (G-3)*w5, 1, 10)                     new card
    S'    = S*(1 + e^w8 * (11-D) * S^-w9 * (e^((1-R)*w10) - 1))
            * hard_penalty * easy_bonus                     grade >= 2
    S'    = min(S, w11 * D^-w12 * ((S+1)^w13 - 1) * e^((1-R)*w14))   lapse
    D'    = clamp(w7*w4 + (1-w7)*(D - w6*(G-3)), 1, 10)

Initial stability by grade is 0.4 / 0.6 / 2.4 / 5.8 days for Again / Hard / Good /
Easy, and a card answered *good* three times at its due dates reaches about 24 days.
The previous hand-tuned constants reached 1.5 days after twelve reviews while
describing themselves as "FSRS-4.5 with rounded constants" — the stability increment
was roughly 20× too small, which is why nothing ever left the same-day regime.

**One documented deviation:** intervals are capped at `MAX_INTERVAL_DAYS` (365).
FSRS permits multi-year intervals; something being studied for a deadline has to come
back inside the horizon it is being studied for.

**Known mismatch, stated plainly:** FSRS's weights are fitted to item-level,
day-scale, self-graded Anki reviews. dojo is applying them to a coarser and noisier
signal than they were trained on — a recall grade the student chose, for an item
whose difficulty the model has never seen. The published defaults are better
provenance than invented constants; they are not a claim that dojo's grades mean what
Anki's do.

## 3. Evidence strength and the seed

A grade is a recall report; the *evidence* behind the attempt is what decides how much
the schedule trusts it ([grading.md](grading.md) §1). The engine's rules:

- A **verified** solve seeds the card from the grade the solve's hint count implies
  (below), exactly as before.
- An item whose strongest evidence is **judged** or **self-reported** — a curriculum
  that declares it cannot machine-check the work — seeds **conservatively**: the
  first card takes the *lower* of the hint-implied grade and "good", and the card
  carries `evidence_kind` so the display never implies verification it does not have.
- Nothing inflates. Weak evidence never earns a longer interval than strong evidence
  would, and the disclosure appears on the card, in `progress`, and in the session's
  own summary line.
- Warm-up grades are self-reported by nature (nobody can measure your memory from
  outside), so the engine says that once, at the level of the claim it supports,
  rather than pretending otherwise.

This is the retention half of the honesty contract: **when in doubt, schedule
sooner.** An over-eager interval is the one failure the student cannot see.

## 4. Grades

Grades follow the Anki convention: 1 = forgot, 2 = hard, 3 = good, 4 = easy. The
suggestion is a prior derived from the session's ladder hints, and it is only a
suggestion — any grade can be typed to override it:

| ladder hints | suggested |
|---|---|
| 0 | 3 (good) |
| 1–2 | 2 (hard) |
| 3+ | 1 (forgot) |

Two details matter. Only `ladder`-kind hints count — a `discussion` question is
exploring, not struggling. And the suggestion tops out at **3**: a hint-free re-solve
is evidence *against* struggle, not evidence of ease, and FSRS's easy bonus
multiplies the whole grown stability by 2.61 — claiming "easy" should be a deliberate
choice, not the default.

**Grades are persisted** on the attempt (`attempts.recall_grade`). They used to be
folded into the card's aggregates and discarded, which made the recall curves the
model exists to enable unreconstructible — and which is also why the rebuild below is
possible at all.

## 5. Warm-ups

`run_warmups` serves the **due queue**, which is global across enrolled curricula and
labelled per curriculum (`dojo warmup --curriculum <id>` narrows it; `--limit N`
drains more; the session always says how many cards remain due). The engine owns the
mechanics: a fresh artifact, an attempt with `kind='warmup'`, no reflection (the
recall grade replaces it), and one transaction for the grade and the card.

The **curriculum** declares what recall means for its items:

| policy | the warm-up is |
|---|---|
| `re-solve` | a blank template for the same item, solved again from scratch |
| `re-derive` | the same item with fresh inputs, or a statement-only variant the curriculum generates |
| `re-justify` | a short written justification, judged against the rubric |

**Quitting a warm-up records nothing** — no attempt row, no card change — because a
deliberate quit means "not now", not evidence of forgetting. A lapse is recorded only
when you grade yourself 1. A card whose item has disappeared (curriculum uninstalled,
item retired) is deferred a day and named, never silently re-pointed at something
else.

## 6. What the scheduler decides

- **Warm-ups:** cards with `due_at <= now`, most overdue first. `dojo day` runs up to
  the curriculum's budget (2 by default); `dojo warmup` up to 3.
- **The next new item:** the curriculum's topic graph, walked in order under its
  prerequisite gate, taking the earliest unsolved item of the first eligible topic.
  Items a curriculum marks ungradable are invisible to the picker until they are
  curated or explicitly chosen — the picker never serves what it cannot assess.
  Explicitly naming an item bypasses the gate, because deliberate choices are exempt.
- **A warm-up never picks a different item:** the card *is* the item.
- **Backfill and repair:** `rebuild_item_cards` replays the attempt log — the event
  source — reconstructing each item's own FSRS state from its submit rows (`kind`,
  `recall_grade`, `submitted_at`), then *spreads* an overdue never-recalled backlog
  over a week (one card a day, driest first). That spread is a capacity decision, not
  a memory claim; `dojo rebuild-cards --spread N` redoes it. Because cards are
  derived, the rebuild is idempotent — and it is also how the curricula migration
  proves itself: the live database's 15 cards must reproduce exactly.

## 7. Session lifecycle

**An attempt row exists if and only if the student submitted.** A session creates its
row on the first submit (pass or fail) and updates it thereafter; quitting before any
submit writes nothing at all. That is what makes `quit` safe as "never mind": it
cannot pollute the learner model with a phantom row for a session that merely looked
at something. `status` therefore carries real information (`correct` /
`wrong_answer` / `error` / `timed_out`) rather than a placeholder.

Workbench state (`workbench/<curriculum>.<item>.state.json`) is retired on submit and
on quit, and every new session starts from a blank artifact. A session killed before
submitting leaves its state file behind and the next invocation **resumes** it — code
and hints intact, the same attempt — which is the only resume path now that `quit` is
a total abandonment. `dojo history` and `dojo show <id>` recover anything from past
sessions.
