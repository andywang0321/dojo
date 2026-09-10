# dojo

An AI-guided interview-prep trainer for people who write production Python and know ML deeply, but never took a formal CS algorithms course. Every day, one command runs the whole loop: warm-up retrievals → a problem picked for your weakest pattern → solve in your own editor with a tutor that never solves for you → an honest grader (isolated judge + empirical profiler + AI review) → reflection, all persisted. dojo is built on one conviction: **the tutor never solves the problem for you — it teaches you to recognize the pattern behind it.**

## Getting started

You need Python ≥ 3.13, [uv](https://docs.astral.sh/uv/), and git. You run dojo from a checkout of this repo:

```bash
git clone <this-repo-url> dojo
cd dojo
uv run dojo
```

That one command does everything on first run:

1. **A one-time setup wizard** starts automatically. It checks for a DeepSeek API key — if `DEEPSEEK_API_KEY` is already in your environment, it's detected and used, no prompt (otherwise you're asked, and Enter skips — more below). Then it asks your name, and finally offers to install a `dojo` command on your PATH.
2. **The daily routine** begins right after: warm-ups (if any are due), then a problem.

After the wizard, every day is just:

```bash
dojo                # the daily routine
dojo learn          # prefer to study a topic first? (optional)
```

The first `uv run dojo` builds the project environment (a minute or two); later runs are instant. If you decline the PATH install, start sessions with `uv run dojo` from the repo — or re-run `dojo setup` to install the command.

**No API key?** The whole pipeline still works with canned AI: `DOJO_AI_BACKEND=mock uv run dojo`. The tutor/reviewer text is fake, everything else (judge, profiler, scheduler, persistence) is real.

## The daily loop

```bash
dojo                        # the daily routine: warm-ups + a scheduler-picked problem
dojo <slug>                 # the same, on a specific problem
dojo warmup                 # due retrievals only
```

Inside a session the prompt always lists the commands: `open` (re-open your editor), `check` (run the visible tests + advisory lint/complexity findings), `hint <what you're stuck on>` (one rung up the ladder), `learn` (park this attempt and study its pattern — or another topic — with the teacher), `submit` (judge → state your complexity, with a double-check step that lets you redo either answer → measure → reflect → review), `quit` (saves your progress; the next session starts fresh from a blank template). A bare question — with or without the `hint` prefix, even starting with another command word — reaches the tutor directly. Every session becomes one attempt row in your history.

After the review you're not done: **`polish`** re-grades your edited code and updates the attempt (a satisfying "perfect" pass), **`discuss <question>`** opens a post-solve conversation (solutions allowed now), **`done`** closes the session.

**The hint ladder** — each `hint` advances one rung; a vague "stuck" forces rung 0 (articulating the blockage is metacognition). The tutor classifies your query: if you're *exploring* rather than blocked — asking conceptual questions, trade-offs, "is this interview-appropriate?" — it answers directly without advancing tiers, and the panel is simply titled "tutor":

| Tier | Name | What it may do |
|------|------|----------------|
| 0 | Articulate the blockage | Ask what you've tried and where exactly you're stuck |
| 1 | Conceptual nudge | Point at a property or invariant, no names |
| 2 | Pattern recognition | Name the problem family |
| 3 | Data structure / invariant | Name the tool and the invariant it maintains |
| 4 | Edge cases | Point at input shapes the code must survive |
| 5 | Skeleton (no code) | Outline the steps in words |

## Learning mode

`dojo learn [topic]` opens a conversation with the **teacher** — a different agent from the tutor. It opens with a short primer (the concept, why it exists, core operations with their complexity, one canonical example), then answers freely, Socratic-style, with ML/statistics analogies. `practice` hands off to the easiest unsolved problem in the topic; `done` ends the session.

Inside a solve, `learn` **parks** your attempt (progress saved, stays 'unsolved') and opens the same conversation on the problem's pattern — accepting the handoff retries **the same problem** with a fresh blank template, so the graded solve stays honest. When the daily scheduler picks a problem from a pattern you've never studied or attempted, dojo offers to learn first — one keystroke declines, and the session proceeds either way.

The never-solve boundary narrows here, deliberately: the teacher's context is the topic and the conversation only — never a problem statement — so it may show topic-canonical code (implementing a heap is legitimate teaching). Grading oracles still never enter any agent's context.

## Everyday commands

```bash
dojo list                   # the problem bank (✓ = curated, ready for the daily loop)
dojo learn [TOPIC]          # learning mode: a topic primer with a practice handoff
dojo progress               # per-pattern proficiency, card schedule, score trends
dojo history                # your attempts, newest first
dojo show <id>              # one attempt in full (hints, code, review; --code for code only)
dojo fetch <slug>           # fetch a LeetCode problem and auto-curate it
dojo user [<name>]          # switch the active user (numbered picker without a name)
dojo setup                  # re-run the setup wizard (change key, reinstall PATH)
```

`dojo help` (or `-h`/`--help`) shows the same short guide in the terminal.

**Power tools** — reachable, just not in the guide: `dojo day <slug>` (the alias for `dojo <slug>`), `dojo check [<slug>]` (visible tests against the active workbench), `dojo report [<slug>] --fix` (AI-audit a problem's curation and re-curate it — normally reached from inside a session), `dojo curate --text "…"` (AI-curate a new problem from a pasted statement). Each documents itself via `dojo <command> --help`.

## Honest caveats

- The profiler reports *evidence* ("consistent with O(n) at tested scales", R², confidence), never proofs; a mismatch between expected / claimed / measured is a signal to investigate. Space fits sample every second probe point — set/dict tables are power-of-two staircases that would otherwise make linear code measure as O(n²) (see docs/grading.md).
- Warm-ups re-solve the least recently solved problem in a pattern; a pattern needs at least one solved problem to warm up.
- `dojo fetch` / `dojo curate` need the API key (the curated oracle is AI-generated and gated by an automated verification suite).
- The teacher has no grader behind it — it's instructed to be humble about uncertainty, but pedagogy is unverified by construction. If a definition feels off, double-check it elsewhere.
- One computer, one user: dojo remembers you in a gitignored config; `dojo user` switches the rare exception.

## Development

```bash
make sync      # install dojo into the project venv (uv sync)
make test      # run the offline test suite (uv run pytest)
```

The bank seeds from `problems/**/*.py` on every run (additive — your data is never reset). Technical docs live in `docs/` (architecture, grading, retention, curation, development); delivered and planned stages live in `roadmap/`.
