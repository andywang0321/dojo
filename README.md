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

1. **A one-time setup wizard** starts automatically. It looks for an API key you already have — DeepSeek, OpenAI or Anthropic, in your environment or a `.env` — and uses it with no prompt (otherwise you're asked, and Enter skips — more below). Then it asks your name, and finally offers to install a `dojo` command on your PATH.
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

After the review the training wheels come off: **`polish`** takes you *back to solving* — `open`, `check` and `submit` are yours again, but questions now go to the post-solve tutor (solutions allowed), which is what you want when you're chasing a better approach. Your next `submit` re-grades the edited code and adds a **version** to the attempt; **`done`** closes the session. Every version you submit is kept, so polishing is never destructive:

```bash
dojo show 42 --revisions     # every version, with its own measurement and review
dojo show 42 --diff          # what changed between the last two
dojo show 42 --rev 1         # the original submission, as it was
dojo show 42 --clean         # the code as the AI read it (dojo's scaffolding removed)
```

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

## Models

dojo talks to DeepSeek by default and also speaks OpenAI and Anthropic. Pick one with `DOJO_AI_BACKEND` (or `DOJO_PROVIDER`), and let `dojo setup` detect whichever key you already have:

```bash
export ANTHROPIC_API_KEY=...      # or OPENAI_API_KEY, or DEEPSEEK_API_KEY
uv run dojo setup --provider anthropic   # optional: pin the choice
uv run dojo                              # runs on Claude from here
```

Override the model globally with `DOJO_MODEL`, or per agent with `DOJO_MODEL_<ROLE>` — the roles are `TUTOR`, `DISCUSSION`, `TEACHER`, `REVIEWER`, `AUDITOR`, `CURATOR`, `CURATION_AUDITOR`, `REFERENCER`. The leak auditor runs on every hint, so it is deliberately cheap (128-token budget, temperature 0); pointing `DOJO_MODEL_AUDITOR` at a small fast model is the intended economy. `DOJO_AI_BACKEND=mock` still runs the entire pipeline offline with canned text.

Every attempt records which backend and model produced its review (`ai_provenance`), so a mock run can never be mistaken for a live one.

## Honest caveats

- **The scale probe** runs your code at increasing sizes (n = 100 … 6,400) and does two things: it reports *failure at scale* — a crash or timeout on an input the judge never reaches, since the judge's cases top out at n ≈ 12 — and it compares your cost curve against the **reference solution's**, measured back-to-back on the same inputs. Comparing the two cancels every constant factor they share, which is why it can tell "grows like the intended solution" from "grows one class faster" when measuring your code alone could not (see docs/grading.md).
- The probe needs a reference to say anything about growth: `dojo reference <slug>` (or `--all`) generates one and refuses to install it unless it agrees with the brute-force oracle everywhere the oracle can run. Without one you still get the scale test, and dojo says so rather than guessing.
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

**Your workbench and debuggers:** sessions edit files in `~/.local/share/dojo/workbench/` — outside the repo, so editor/debugger tooling never collides with git. Every workbench file starts with a shebang pointing at dojo's venv, ends with a fenced `if __name__ == "__main__"` block built from that problem's visible examples, and dojo generates self-contained IDE config *inside* the workbench folder — so **Run and Debug do something on every problem**: pressing Run prints one line per example (`case 1: ok  got=True want=True`), and pressing Debug breaks inside your function on the same inputs. `dojo open` opens that folder in VSCode-family editors and Zed with the debugger already wired (VSCode: "dojo: debug the active workbench file" + F5; Zed: run `debugger: start` or F4 and pick the dojo profile). The block is dojo's, not yours: it's stripped from everything the AI reads, and the judge never runs it. `ipykernel` and `debugpy` ship in dojo's venv, so notebook kernels and the debug adapter are already present. `check` shows everything your code prints — prints are debugging statements, and the checking loop is the debugging loop.

The bank seeds from `problems/**/*.py` on every run (additive — your data is never reset). Every live AI exchange (prompts + raw responses) is appended to the gitignored debug log at `data/logs/dojo.log` for post-hoc debugging; it clears automatically on major version bumps. Technical docs live in `docs/` (architecture, grading, retention, curation, development); delivered and planned stages live in `roadmap/`.
