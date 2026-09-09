# next — learning mode, setup streamlining, ergonomics

Planned stage, awaiting design conversations. Each item below is an idea, not a spec — design decisions get their own discussion before implementation.

## 1. Learning mode

The audience has no formal CS education: a linked-list problem doesn't register as a linked-list problem until linked lists exist as a concept. Learning mode is an AI-taught topic primer:

- Pick a topic (from the pattern taxonomy: stacks, linked lists, graphs, ...), and the tutor agent *actively teaches* it — explaining concepts, examples, and trade-offs in a conversation (chat-like: the student asks questions, the agent answers and probes understanding).
- When the student feels ready (or when the agent judges readiness), jump straight into problem mode with an **easy problem on that topic**, with the session starting from a blank template as usual.
- Open design questions to settle: how learning sessions persist (chat log on a new table? per-pattern "learned" state?), how the never-solve boundary applies to teaching (the agent must explain, not hand over solutions), how the topic → easy-problem pick works, and how learning mode interacts with the scheduler (does learning create cards? count as studying?).

## 2. Setup streamlining

`dojo init` is under-explained and under-automated. Ideas:

- An interactive first-run setup (wizard-style): detect missing API key → offer to write `.env`; ask for the user's name; explain what init does in plain words; verify the pipeline with a mock backend before the first real day.
- Make `dojo init` itself self-explanatory (summary output: "created the database, imported N problems, registered user X, backfilled M cards — next: `dojo day`").
- Decide what belongs in setup vs. what stays manual (secrets handling, mock-backend fallback, re-running init safely).

## 3. Ergonomics: `dojo` on PATH

Nobody wants `cd dojo && uv run` before every command. Ideas:

- During setup, install a `dojo` entry point onto PATH (uv tool install / a `~/.local/bin` symlink / shell alias) so the daily loop is just `dojo day`.
- Consider how updates flow (reinstall on pull?), how the venv is shared with the PATH entry, and what happens on machines where `uv` itself isn't global.

## Backlog (unchanged)

- TUI polish (Textual) — only if the CLI loop proves insufficient.
- Two-machine sync.
- Warm-up problem variants (transfer, not recognition — see docs/retention.md).
- A web UI — only if the CLI proves insufficient, never first.
