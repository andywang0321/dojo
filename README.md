# dojo

An AI-guided interview-prep trainer for people who write production Python and know ML deeply, but never took a formal CS algorithms course. Every day, one command runs the whole loop: warm-up retrievals → a problem picked in roadmap order (the NeetCode 150 progression, prerequisites gated) → solve in your own editor with a tutor that never solves for you → an honest grader (isolated judge + empirical profiler + AI review) → reflection, all persisted. dojo is built on one conviction: **the tutor never solves the problem for you — it teaches you to recognize the pattern behind it.**

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

Inside a session, the prompt shows the commands as **virtual text** right after your cursor — they vanish the moment you type: `open`, `check`, `learn`, `submit`, `quit`. Anything else you type is a question to the tutor — the `hint` command is gone; you just ask. **Submitting records an attempt; `quit` records nothing at all** — no row, no hints, no lapse. That is deliberate: glancing at a problem, poking at a feature, or changing your mind should not land in your history. A session that dies (crash, closed laptop) is resumed by running the same command again; the workbench state survives.

After the review you're not done: **`polish`** re-grades your edited code and updates the attempt (a satisfying "perfect" pass), and any question you type opens a post-solve conversation (solutions allowed now). **`done`** closes the session.

**The hint ladder** — each question advances one rung when you're stuck; a vague "stuck" forces rung 0 (articulating the blockage is metacognition). The tutor classifies your query: if you're *exploring* rather than blocked — asking conceptual questions, trade-offs, "is this interview-appropriate?" — it answers directly without advancing tiers. Every AI answer renders as **Markdown** in the terminal — headings, lists, and syntax-highlighted code blocks — under a dim title line (`tutor · tier 2 — pattern recognition`):

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

Inside a solve, `learn` **abandons** the in-progress attempt (nothing recorded) and opens the same conversation on the problem's pattern — accepting the handoff retries **the same problem** with a fresh blank template, so the graded solve stays honest. When the daily scheduler picks a problem from a pattern you've never studied or attempted, dojo offers to learn first — one keystroke declines, and the session proceeds either way.

The never-solve boundary narrows here, deliberately: the teacher's context is the topic and the conversation only — never a problem statement — so it may show topic-canonical code (implementing a heap is legitimate teaching). Grading oracles still never enter any agent's context.

## Everyday commands

```bash
dojo list                   # the problem bank (✓ = curated, ready for the daily loop)
dojo roadmap                # the progression tree: solved · next up · locked
dojo learn [TOPIC]          # learning mode: a topic primer with a practice handoff
dojo progress               # per-pattern proficiency, card schedule, score trends
dojo history                # your attempts, newest first
dojo show <id>              # one attempt in full (hints, code, review; --code for code only)
dojo fetch <slug>           # fetch a LeetCode problem and auto-curate it
                             #   `dojo fetch --all` lands the whole roadmap without curating
dojo user [<name>]          # switch the active user (numbered picker without a name)
dojo setup                  # re-run the setup wizard (change key, reinstall PATH)
```

## The progression

The daily pick follows the **NeetCode 150 roadmap** (`data/roadmap.toml`, vendored with provenance): 18 technique groups in prerequisite order, each an ordered problem ladder. The scheduler walks the groups top-down and serves the earliest unsolved ladder problem of the first group whose prerequisites are all complete — `dojo roadmap` draws the tree itself — groups as branches, each group's ladder as leaves (✓ solved · → next up · ○ ready · · not fetched), the next-up group expanded by default (`--expand <pattern>` / `--all` open more, `--table` restores the stats view). Problems fetched but not yet on the ladder, and dojo's own hand-written problems, are served after the ladder in the bank is done. Explicit `dojo <slug>` always bypasses the gate — deliberate choices are exempt.

`dojo help` (or `-h`/`--help`) shows the same short guide in the terminal.

**Power tools** — reachable, just not in the guide: `dojo day <slug>` (the alias for `dojo <slug>`), `dojo check [<slug>]` (visible tests against the active workbench), `dojo report [<slug>] --fix` (AI-audit a problem's curation and re-curate it — normally reached from inside a session), `dojo curate --text "…"` (AI-curate a new problem from a pasted statement). Each documents itself via `dojo <command> --help`.

## Honest caveats

- The profiler reports *evidence* ("consistent with O(n) at tested scales", R², confidence), never proofs; a mismatch between expected / claimed / measured is a signal to investigate. When the data cannot separate two classes it says so — a measured `O(n)…O(n log n)` is a range, not a verdict, and a claim inside it is not flagged. Time is measured with no tracer running (tracemalloc's own bookkeeping used to inflate the slope and make allocation-heavy linear code read as O(n log n)); space is measured separately, sampling every second probe point because set/dict tables are power-of-two staircases that would otherwise make linear code measure as O(n²) (see docs/grading.md).
- Warm-ups re-solve the least recently practised problem in a pattern (consecutive warm-ups rotate once a pattern has more than one solved problem); a pattern needs at least one solved problem to warm up. Quitting a warm-up records nothing — mark a lapse yourself with grade 1.
- `dojo fetch` / `dojo curate` need the API key (the curated oracle is AI-generated and gated by an automated verification suite).
- The teacher has no grader behind it — it's instructed to be humble about uncertainty, but pedagogy is unverified by construction. If a definition feels off, double-check it elsewhere.
- One computer, one user: dojo remembers you in a gitignored config; `dojo user` switches the rare exception.

## Development

```bash
make sync      # install dojo into the project venv (uv sync)
make test      # run the offline test suite (uv run pytest)
```

**Updating:** every `dojo` run fast-forwards the repo and refreshes dependencies automatically (nothing is printed unless something changed). `dojo update` does it on demand; `dojo update --force` discards local changes. `DOJO_NO_AUTO_UPDATE=1` opts out.

**Your workbench and debuggers:** sessions edit files in `~/.local/share/dojo/workbench/` — outside the repo, so editor/debugger tooling never collides with git. Every workbench file starts with a shebang pointing at dojo's venv, and dojo generates self-contained IDE config *inside* the workbench folder: `dojo open` opens that folder in VSCode-family editors and Zed with the debugger already wired (VSCode: "dojo: debug the active workbench file" + F5; Zed: run `debugger: start` or F4 and pick the dojo profile). `ipykernel` and `debugpy` ship in dojo's venv, so notebook kernels and the debug adapter are already present. `check` shows everything your code prints — prints are debugging statements, and the checking loop is the debugging loop.

The bank seeds from `problems/**/*.py` on every run (additive — your data is never reset). Every live AI exchange (prompts + raw responses) is appended to the gitignored debug log at `data/logs/dojo.log` for post-hoc debugging; it clears automatically on major version bumps. Technical docs live in `docs/` (architecture, grading, retention, curation, development); delivered and planned stages live in `roadmap/`.
