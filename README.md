# dojo

A local practice engine, powered by AI, that turns "I want to learn X" into a daily
habit that sticks.

dojo is built on four claims:

1. **Spaced repetition.** FSRS-4.5 over what you actually practised decides what
   comes back, and when.
2. **Evidence.** dojo produces the strongest honest evidence it can about what you
   just did, says how strong that evidence is, and lets only that evidence move the
   schedule. "Unresolved", "unjudged" and "not measurable here" are outcomes, not
   failures — and nothing is ever claimed that the evidence does not support.
3. **AI personalization.** A tutor that guides you and never solves for you, a
   teacher for topics you have not met, a reviewer that critiques what you wrote.
4. **AI curriculum generation.** You are not expected to be an expert in the thing
   you are learning. Point dojo at a source you trust and it can help build the
   curriculum — the outline, the exercises, the checks — and then tailor it to you.

The result is a loop: you practise, dojo gathers evidence, the evidence moves the
schedule, the schedule picks the next thing, and the agents adapt the curriculum
around how you are actually doing.

> **Status: this branch is the rebuild.** You are reading `curricula`, where
> dojo is being split into an **engine** (this repository) and **curricula**
> (separate repositories you enroll). `main` still carries the working trainer with
> the NeetCode 150 built in, and it is what to run today. Everything below describes
> the engine as the split lands; see [`roadmap/v0.14.md`](roadmap/v0.14.md).

## What you practise comes from a curriculum

dojo itself is subject-agnostic: it schedules, asks, grades, measures, critiques and
remembers. The subject arrives as a **curriculum** — a local, versioned bundle that
declares its topics, its exercises, how a submission is checked, what is worth
measuring, what a warm-up means, and what to call all of that on screen.

Curricula are their own repositories, so anyone can write one (the way you would
write a Neovim plugin) — and **dojo does not build them**. It ships the
specification and a kit for authors and their AI agents
([`curriculum-kit/`](curriculum-kit/)); everything else is yours:

```bash
dojo enroll github.com/<you>/dojo-curriculum-neetcode-150
dojo enroll github.com/<you>/dojo-curriculum-jax
dojo curricula                  # what is installed, what is enrolled
dojo unenroll jax               # pause it; your history stays
```

The engine's vocabulary is **curriculum → topic → item → attempt → evidence →
card**. Your curriculum supplies its own words for those — one calls them Patterns
and Problems, another Modules and Labs — and dojo uses them on screen.

**Enrolled in more than one?** dojo still starts with one command:

```bash
dojo
# What would you like to study today?
#   1. NeetCode 150
#   2. JAX          [Enter = 2]
```

One keystroke, remembered until you change it. A bare `dojo` never asks twice, and
`dojo history`, `dojo progress`, `dojo outline` and the like stay *global* — pulling
up your history should not interrogate you about today's focus. The warm-up queue is
global too: a card that is due is due, whichever curriculum it came from.

## Getting started

You need Python ≥ 3.13, [uv](https://docs.astral.sh/uv/), and git.

```bash
git clone <this-repo-url> dojo
cd dojo
uv run dojo
```

That one command does everything on first run:

1. **A one-time setup wizard** looks for an API key you already have — DeepSeek,
   OpenAI or Anthropic, in your environment or a `.env` — uses it with no prompt
   (otherwise you are asked, and Enter skips), asks your name, and offers to install
   a `dojo` command on your PATH.
2. **It offers a curriculum to enroll in.** An engine with nothing to practise says
   so and points at `dojo enroll`; it never pretends to have work for you.
3. **The daily routine** begins: warm-ups if any are due, then the next item.

After that, every day is just:

```bash
dojo                # the daily routine
dojo learn          # prefer to study a topic first? (optional)
```

**No API key?** The whole pipeline runs with canned AI:
`DOJO_AI_BACKEND=mock uv run dojo`. The tutor/reviewer text is fake; the judge, the
measurement, the scheduler and the persistence are real.

## The daily loop

```bash
dojo                        # the daily routine: warm-ups + the next item
dojo <item>                 # that item — with the warm-up queue *offered*, not assumed
dojo warmup                 # due retrievals only (--curriculum jax to narrow it)
```

**When you name an item, you get that item.** `dojo two_sum` does not quietly serve
three other things first: if warm-ups are due it asks — *You have 3 warm-ups due —
do the first 2 now? [y/N]* — and either way your item is next. Answering no costs
nothing (the cards stay due; FSRS is unaffected), and `--skip-warmup` skips even the
question.

Inside a session the prompt shows its commands as **virtual text** right after your
cursor — they vanish the moment you type: `open`, `check`, `learn`, `submit`,
`quit`. Anything else you type is a question to the tutor; the `hint` command is
gone, you just ask. **Submitting records an attempt; `quit` records nothing at
all** — no row, no hints, no lapse. Glancing at something, poking at a feature or
changing your mind should not land in your history. A session that dies (crash,
closed laptop) resumes by running the same command again; the state survives.

After the review the training wheels come off: **`polish`** takes you *back to
solving* — `open`, `check` and `submit` are yours again, but questions now go to the
post-solve tutor (solutions allowed), which is what you want when you are chasing a
better approach. Your next `submit` re-grades the edited work and adds a **version**
to the attempt; **`done`** closes the session. Polishing is never destructive:

```bash
dojo show 42 --revisions     # every version, with its own measurement and review
dojo show 42 --diff          # what changed between the last two
dojo show 42 --rev 1         # the original submission, as it was
dojo show 42 --clean         # the work as the AI read it (dojo's scaffolding removed)
```

**The hint ladder** — each question advances one rung when you are stuck; a vague
"stuck" forces rung 0, because articulating the blockage is the metacognition. A
curriculum declares what its rungs are allowed to say, and every rung is audited for
leaks before you see it:

| Tier | Name | What it may do |
|------|------|----------------|
| 0 | Articulate the blockage | Ask what you've tried and where exactly you're stuck |
| 1 | Conceptual nudge | Point at a property or invariant, no names |
| 2 | Pattern recognition | Name the family of technique |
| 3 | Data structure / invariant | Name the tool and the invariant it maintains |
| 4 | Edge cases | Point at input shapes the work must survive |
| 5 | Skeleton (no code) | Outline the steps in words |

Every AI answer renders as **Markdown** in the terminal — headings, lists,
syntax-highlighted code — under a dim title line (`tutor · tier 2 — pattern
recognition`).

## Learning mode

`dojo learn [topic]` opens a conversation with the **teacher**, a different agent
from the tutor. It opens with a short primer (the concept, why it exists, core
operations with their complexity, one canonical example), then answers freely,
Socratic-style, with ML/statistics analogies. `practice` hands off to the easiest
unsolved item in the topic; `done` ends the session.

Inside a solve, `learn` **abandons** the in-progress attempt (nothing recorded) and
opens the same conversation on the item's topic — accepting the handoff retries
**the same item** with a fresh template, so the graded solve stays honest. When the
scheduler picks an item from a topic you have never studied or attempted, dojo
offers to learn first; one keystroke declines, and the session proceeds either way.

The never-solve boundary narrows here, deliberately: the teacher's context is the
topic and the conversation only — never an item's statement — so it may show
topic-canonical code (implementing a heap is legitimate teaching). Grading oracles
never enter any agent's context, in any curriculum, ever.

## Everyday commands

```bash
dojo list                   # everything enrolled, ✓ = ready for the daily loop
dojo outline                # the progression tree: done · next up · locked
dojo learn [TOPIC]          # learning mode: a primer with a practice handoff
dojo progress               # per-topic proficiency, card schedule, score trends
dojo history                # attempts, oldest first (newest last); --limit N
dojo show <id>              # one attempt in full (--code, --clean, --revisions, --diff)
dojo curricula              # installed + enrolled curricula, with their health
dojo enroll <url|path>      # install and enroll a curriculum
dojo user [<name>]          # switch the active user
dojo setup                  # re-run the setup wizard (change key, reinstall PATH)
```

## What dojo knows about what you did

Every attempt carries **evidence**, and evidence has a kind and a strength:

| kind | what it establishes | how |
|---|---|---|
| **verified** | the work is correct | cases run against an oracle in an isolated subprocess |
| **measured** | how it scales | a paired comparison against a reference — a ratio, never an absolute fit |
| **judged** | how good it is | an AI review against the curriculum's rubric |
| **self-reported** | what you say | your claimed complexity, your recall grade |

dojo displays which one it has and never upgrades it silently. A judgment is
*advisory*: it shapes the review you read, and it does not become a fact because a
model said so. If a judgment would *gate* something — mark a unit complete, or let
an interval grow — an independent audit pass has to agree, and disagreement is
reported as unresolved rather than smoothed over.

**If your network drops mid-session, dojo says so and carries on.** You get
"I'm having trouble connecting to the AI backend — is the network connection ok?"
and one line saying what did not answer (the tutor, the review, the leak check).
Nothing is recorded for the call that failed, your tier does not move, and `dojo
check`, the judge, the measurement and the scheduler keep working offline. A stalled
connection cannot freeze a session either: each AI call gives up after its role's
bound (60s interactive, 180s long-form) instead of the SDK's default ten minutes. A
*rejected* call is still reported as itself, so a wrong API key or an exhausted
quota never reads as bad wifi. Work whose judgment could not run is recorded as
**submitted, unjudged** — never blocked, never faked.

## Models

dojo talks to DeepSeek by default and also speaks OpenAI and Anthropic. Pick one
with `DOJO_AI_BACKEND` (or `DOJO_PROVIDER`), and let `dojo setup` detect whichever
key you already have:

```bash
export ANTHROPIC_API_KEY=...      # or OPENAI_API_KEY, or DEEPSEEK_API_KEY
uv run dojo setup --provider anthropic   # optional: pin the choice
uv run dojo                              # runs on Claude from here
```

Override the model globally with `DOJO_MODEL`, or per agent with
`DOJO_MODEL_<ROLE>` — the roles are `TUTOR`, `DISCUSSION`, `TEACHER`, `REVIEWER`,
`AUDITOR`. The leak auditor runs on
every hint, so it is deliberately cheap (128-token budget, temperature 0); pointing
`DOJO_MODEL_AUDITOR` at a small fast model is the intended economy.

Every request is also **time-bounded**, because the SDKs are not: they default to a
600-second read timeout with two retries, which a connection that opens and never
answers (captive portal, dropped VPN) turns into half an hour of a frozen terminal.
The interactive roles give up after 60 seconds; the long-form ones after 180.
`DOJO_TIMEOUT=<seconds>` overrides every role.

Every attempt records which backend and model produced its review
(`ai_provenance`), so a mock run can never be mistaken for a live one.

## Your workbench and debuggers

Sessions edit files in `~/.local/share/dojo/workbench/` — outside any repository, so
editor and debugger tooling never collides with git. Every artifact starts with a
shebang pointing at the interpreter the curriculum declares, ends with a fenced
`if __name__ == "__main__"` block built from that item's own visible examples, and
dojo generates self-contained IDE config *inside* the workbench folder — so **Run
and Debug do something on every item**: Run prints one line per example
(`case 1: ok  got=True want=True`), and Debug breaks inside your function on the
same inputs. `dojo open` opens that folder in VSCode-family editors and Zed with the
debugger already wired (VSCode: "dojo: debug the active workbench file" + F5; Zed:
run `debugger: start` and pick the dojo profile). The examples block is dojo's, not
yours: it is stripped from everything the AI reads, and the judge never runs it.
`check` shows everything your work prints — prints are debugging statements, and the
checking loop is the debugging loop.

## Writing a curriculum

A curriculum is a directory with a `curriculum.toml` and some Python:

```
my-curriculum/
  curriculum.toml     # topics, items, policies, display words
  items/              # what the student opens and submits
  checks/             # the visible tests they can run
  assessment/         # oracles, generators, references — never shown to any agent
  measure/            # how this subject is measured (optional)
```

```bash
cp -r <dojo>/curriculum-kit/example my-subject   # start from the complete tiny example
dojo enroll ./my-subject                        # enroll = install + validate; it refuses anything that dangles
```

The whole format is documented in [`docs/curricula.md`](docs/curricula.md), and
[`curriculum-kit/`](curriculum-kit/) is the authoring interface: the example
curriculum, an `AGENTS.md` template for a curriculum repository, and four prompts for
an AI agent — plan a curriculum from a source, author an item, audit a curriculum,
port an existing corpus.

The short version of what makes it honest: a curriculum declares what its evidence
*means*, and the engine refuses to pretend otherwise. If your subject cannot be
machine-graded, you say so and the items are judged or self-reported — clearly
labelled, never dressed up as verification.

And if you are learning the subject yourself, you do not have to author it alone:
point an agent at the source you trust with the kit's planning prompt, and that is the
fourth claim above — generation as a third-party workflow, not an engine feature.

## Development

```bash
make sync      # install dojo into the project venv (uv sync)
make test      # the offline test suite (uv run pytest)
make version   # write the version this commit will have into pyproject.toml
```

Two branches are live: `main` is the trainer people practise on every day, and
`curricula` is this rebuild. If you are working on the rebuild, read
[`HANDOFF.md`](HANDOFF.md) first and [`AGENTS.md`](AGENTS.md) §0 before you commit
anything — the branch check is mandatory, not a formality.

**Updating:** every `dojo` run fast-forwards the engine and refreshes dependencies
automatically (nothing prints unless something changed). `dojo update` does it on
demand, `dojo update --force` discards local changes, and `DOJO_NO_AUTO_UPDATE=1`
opts out. Enrolled curricula update from their own sources.

Technical docs live in [`docs/`](docs/) — architecture, curricula, grading,
retention, authoring, development — and the phase plan in [`roadmap/`](roadmap/).
