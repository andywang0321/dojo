# Retention: the scheduler and warm-ups

## FSRS-lite

Each (user, pattern) card carries **stability S** (memory strength, days) and **difficulty D** (1–10), plus a due date. Recall probability follows the FSRS forgetting curve

    R(t, S) = (1 + FACTOR * t / S) ** DECAY

with FSRS's `FACTOR = 19/81` and `DECAY = -0.5` (so R ≈ 0.90 at t = S — the default review interval equals the stability). Constants live at the top of `scheduler.py` (`S0`, `D0`, `TARGET_R`) and are documented; the whole model is ~50 lines, deliberately.

Grades follow the Anki convention: 1 = forgot, 2 = hard, 3 = good, 4 = easy. Successful recalls grow stability (more for easy, less for hard cards, damped as S grows) and ease difficulty; lapses shrink stability and raise difficulty. Reviewed-too-early (R ≈ 1) deliberately yields no growth — that's the model, not a bug.

## What the scheduler decides

- **Due warm-ups:** cards with `due_at <= now`, most overdue first (`dojo day` runs up to 2, `dojo warmup` up to 3).
- **Which problem to warm up:** the *least recently solved* correct problem in the pattern — oldest memory, most worth retrieving.
- **Which problem to solve next (v0.10):** the roadmap order — patterns are walked in progression order under the hard prereq gate, and within a pattern the earliest unsolved ladder problem wins (ladder problems are LeetCode-numbered; dojo's own problems are the fallback once the ladder is exhausted). Stability still governs warm-up scheduling.
- **Backfill:** `dojo init` creates cards for every (user, pattern) with a solved attempt, due immediately.

## Warm-up semantics

`run_warmups` forces a fresh template (re-solve from scratch), creates an attempt with `kind='warmup'`, skips reflection (the recall grade replaces it), and quits record a lapse. The suggested grade derives from hints used: 0 hints → 4, 1 → 3, 2+ → 2. A pattern card without a solved problem is deferred a day.

## Session lifecycle

One `dojo day` invocation = one attempt row. Workbench state (`workbench/<slug>.state.json`) is per (slug, kind) and retired on submit and on quit; every new session starts from a blank template. Quitting persists code + hints to the abandoned row. `dojo history` / `dojo show <id>` recover anything from past sessions.
