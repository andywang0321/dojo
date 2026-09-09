# next — learning mode

Planned stage, awaiting a design conversation. The setup/ergonomics work formerly here has moved to [v0.5](v0.5.md) with a settled design.

## Learning mode

The audience has no formal CS education: a linked-list problem doesn't register as a linked-list problem until linked lists exist as a concept. Learning mode is an AI-taught topic primer:

- Pick a topic (from the pattern taxonomy: stacks, linked lists, graphs, ...), and the tutor agent *actively teaches* it — explaining concepts, examples, and trade-offs in a conversation (chat-like: the student asks questions, the agent answers and probes understanding).
- When the student feels ready (or when the agent judges readiness), jump straight into problem mode with an **easy problem on that topic**, with the session starting from a blank template as usual.
- Entry contract already settled: `dojo learn [topic]`; no topic → a numbered picker over the pattern taxonomy (the same picker component as `dojo user` in v0.5).
- Open design questions to settle: how learning sessions persist (chat log on a new table? per-pattern "learned" state?), how the never-solve boundary applies to teaching (the agent must explain, never hand over solutions), how the topic → easy-problem pick works, and how learning mode interacts with the scheduler (does learning create cards? count as studying?).

## Backlog (unchanged)

- TUI polish (Textual) — only if the CLI loop proves insufficient.
- Two-machine sync.
- Warm-up problem variants (transfer, not recognition — see docs/retention.md).
- A web UI — only if the CLI proves insufficient, never first.
