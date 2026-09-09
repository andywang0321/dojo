# dojo

An AI-guided interview-prep trainer for two PhDs (data science, bioengineering) who write production Python and know ML deeply, but never had a formal CS algorithms course. dojo is built on one conviction: **the tutor never solves the problem for you — it teaches you to recognize the pattern behind it.**

Every day, `dojo day` runs the whole loop:

- **Warm up** — the scheduler re-opens a previously solved problem, from scratch, to keep the pattern alive (spaced repetition).
- **Solve** — a fresh problem picked for you (weakest pattern first), in your own editor.
- **Grade** — an isolated judge runs visible + generated + oracle-checked tests; an empirical profiler *measures* your time/space growth; an AI reviewer scores a rubric; static analysis (cyclomatic complexity + lint) rides along.
- **Retain** — you state your complexity before the machine measures it, reflect, and everything lands in your attempt history — the durable asset.

Three pillars: a **never-solve tutor** (gated hint ladder, leak-audited), a **grading engine** (judge + profiler + reviewer + static analysis), and a **retention engine** (FSRS-lite spaced repetition over pattern cards).

## Quick start

Prerequisites: Python ≥ 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
make sync                  # install dojo into the project venv
uv run dojo                # first run: a one-time setup wizard, then the daily routine
dojo                       # afterwards (the wizard can put `dojo` on your PATH)
```

The setup wizard asks for your DeepSeek API key (masked, saved to a gitignored `.env` — press Enter to skip and use `DOJO_AI_BACKEND=mock` later), your name, and offers to install a `dojo` wrapper on your PATH so every day is just `dojo`. No API key? `DOJO_AI_BACKEND=mock uv run dojo` runs the entire pipeline with canned responses — everything except real AI text works.

One computer, one user: dojo remembers you in a gitignored config. `dojo user` switches the rare exception, `git switch`-style.

## The daily loop

```bash
dojo                        # the daily routine: warm-ups + a scheduler-picked problem
dojo <slug>                 # the same, on a specific problem
dojo warmup                 # due retrievals only
```

Inside a session the prompt always lists the commands: `check` (run the visible tests), `hint <what you're stuck on>` (one rung up the ladder), `open` (re-open your editor), `submit` (judge → self-report → measure → review → reflect), `quit` (saves your progress; the next session starts fresh from a blank template). Every session becomes one attempt row in your history.

**The hint ladder** — each `hint` advances one rung; a vague "stuck" forces rung 0 (articulating the blockage is metacognition):

| Tier | Name | What it may do |
|------|------|----------------|
| 0 | Articulate the blockage | Ask what you've tried and where exactly you're stuck |
| 1 | Conceptual nudge | Point at a property or invariant, no names |
| 2 | Pattern recognition | Name the problem family |
| 3 | Data structure / invariant | Name the tool and the invariant it maintains |
| 4 | Edge cases | Point at input shapes the code must survive |
| 5 | Skeleton (no code) | Outline the steps in words |

## Other commands

```bash
dojo list                   # the problem bank (✓ = curated, ready for the daily loop)
dojo progress               # per-pattern proficiency, card schedule, score trends
dojo history                # your attempts, newest first
dojo show <id>              # one attempt in full (hints, code, review; --code for code only)
dojo check [<slug>]         # visible tests against the active workbench
dojo user [<name>]          # switch the active user (numbered picker without a name)
dojo setup                  # re-run the setup wizard (change key, reinstall PATH)
dojo curate --text "…"      # AI-curate a new problem from a pasted statement
dojo fetch <slug>           # fetch a LeetCode problem and auto-curate it
```

## Honest caveats

- The profiler reports *evidence* ("consistent with O(n) at tested scales", R², confidence), never proofs; a mismatch between expected / claimed / measured is a signal to investigate.
- Warm-ups re-solve the least recently solved problem in a pattern; a pattern needs at least one solved problem to warm up.
- `dojo fetch` / `dojo curate` need the API key (the curated oracle is AI-generated and gated by an automated verification suite).

## Where the rest lives

- `docs/` — technical documentation: architecture, grading, retention, curation, development.
- `roadmap/` — delivered stages and what's planned next.
- `AGENTS.md` — working conventions for humans and AI agents in this repo.
