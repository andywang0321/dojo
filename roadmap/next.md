# next — backlog

Learning mode has moved to [v0.8](v0.8.md) and is being implemented.

## Proposals from the v0.8 design audit (uncommitted, in rough priority order)

1. **Judge ground-truth anchor + false-failure banner.** For LeetCode-fetched problems, validate the AI oracle against LeetCode's own judge once at curation time and store the verdict in the proposal provenance (dual-oracle agreement stays, but as a filter before the real check). In `_submit`, a distinct message when a submission fails only generated/oracle cases (visible cases pass) — "this could be a curation bug — `dojo report` audits it" — instead of a plain ✗. Converts the worst failure mode from silent trust loss into a visible, fixable event.
2. **Warm-up rotation floor.** When a pattern has ≥2 solved problems, warm up on a *different* problem than the previous cycle for that card — breaks the worst of the recognition problem cheaply and sets up real variants.
3. **Streak + reminder.** Status line shows consecutive practice days; the setup wizard offers a daily cron/launchd entry with the same consent UX as the PATH wrapper. The actual adoption risk is the habit, not the loop's interior.
4. **Consolidate `profile` into `history`** (near-duplicate commands; keep `progress` for patterns, `show <id>` for detail) and hold the session command list ≤7. ✅ shipped in v0.9 — `profile` is now a hidden alias of `history`.
5. **Reviewer calibration in `dojo progress`.** Reviewer scores vs. subsequent warm-up grades per pattern, plus hint-count correlation — an audit loop for the *reviewer*, mirroring what `report` does for the *curator*.
6. **Learner-model steering.** Stall detection (tier at abandon, hint counts) feeding problem selection and the proactive learn offer — close the loop on "the learner model is the asset".
7. **Write-up.** The never-solve-as-architecture idea, the honesty contract, and the grader self-audit loop are worth a public write-up; the design docs are the second-most-valuable artifact.
8. **Terminal rendering polish.** ✅ shipped in v0.10.3 (the markdown flip: rich Markdown + syntax highlighting on all AI prose, dim title lines instead of Panels). Render AI output with rich `Markdown` (headings, lists, emphasis) instead of the flatten-then-strip `de_markdown` display path, and syntax-highlight code blocks with rich `Syntax` (teacher/discussion output, `dojo show` code panels). Keep `de_markdown` for transcript persistence and the non-TTY fallback, and pin the plain-text prompt contract tests when the display path changes. The prompt-color regression (`[bold cyan]dojo ›` flattening under prompt_toolkit) shipped fixed in v0.8.1 via rich-markup→ANSI conversion.

## Backlog (unchanged)

- TUI polish (Textual) — only if the CLI loop proves insufficient.
- Two-machine sync.
- Warm-up problem variants (transfer, not recognition — see docs/retention.md).
- A web UI — only if the CLI proves insufficient, never first.
