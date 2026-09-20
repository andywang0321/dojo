# next — backlog

The v0.10 progression, the [v0.11](v0.11.md) correctness stage (attempt
lifecycle, warm-up, retention) and the [v0.12](v0.12.md) measurement stage have
shipped. The profiler is now a paired scale probe against a canonical reference,
and its failures are findings rather than blanks.

**2026-09-19 — a full audit of the v0.12 codebase landed in
[docs/audit-v0.12.md](../docs/audit-v0.12.md).** It re-checked every finding
below, added ~40 more (with reproduced evidence), and ordered the work in its §6.
Two stages are planned from it: [v0.13](v0.13.md) (session continuity, the
workbench file, providers — its Stage 0 is the trust subset) and
[v0.14](v0.14.md) (curricula: JAX, then Rust). **Fuzzing with shrinking**,
deferred from v0.12 to "v0.13", is deliberately *not* on that path: it stays
here, below the stages, rather than blocking the curriculum work.

## v0.11 audit findings (from the handoff code audit)

Ordered roughly by how much trust they cost. Items marked **→ v0.11** are
being fixed in the current stage rather than deferred.

*Status after the v0.12 audit, updated when v0.13 Stage 0 shipped: items **1, 3,
4, 5 and 7 are closed**, item 11 is **half-closed** (the CLI smoke tests exist;
`_cmd_curate`/`_cmd_report`/`_cmd_reference`/`_cmd_update`/`_cmd_user` still have
no direct test), and items 2 (the never-solve guard is still a five-string grep),
6, 8, 9, 10, 12 and 13 remain open — 8/12/13 are content and provenance, handled
in [v0.14](v0.14.md) Increment 1.*

1. **The leak audit is fail-open.** `tutor._audit` returns `1` ("clean") when
   the auditor returns non-JSON, omits `rating`, or returns a non-int — so a
   tutor response containing a complete solution is **delivered** in all three
   failure modes (verified by execution: a `two_sum` implementation reached the
   student in 3/3 cases). Make the audit fail-closed with a visible signal, and
   add one test per failure mode. Related: a discarded leak is already in
   `data/logs/dojo.log` (`chat_json` logs the raw response *before* the discard
   decision), so "discarded, never shown" is false with respect to the log.
2. **The never-solve guard test is a token grep, not a boundary check.**
   `tests/test_never_solve.py` greps five literal strings; it stays green if a
   full solution is passed as the `statement` argument, if a new module name
   appears (`dojo/solutions.py`), if `JUDGE_CASES`/`PROFILER_INPUTS` are used
   (not in the list), or via a transitive import through `dojo.db`/`dojo.config`
   (never scanned). Replace with an import-graph assertion plus a provenance
   check on the tutor call site.
3. **The judge's stdout channel is only half-isolated.** `isolated()` swaps
   `sys.stdout` but not file descriptor 1: `os.write(1, …)`, `os.system`, or a
   child process inherits into the protocol channel, corrupts the result JSON,
   and `json.loads` then raises **out of `run_cases`** — killing the session.
   Same bug class as the v0.10.1 print fix. Capture at the fd level.
4. **Case-level errors are mislabeled.** `JudgeReport.status` is computed from
   `n_passed` alone, so a case whose handler caught an exception reports
   `wrong_answer`; the `error` status is unreachable for case errors.
5. **No transport-error handling in the daily loop.** `cli.main` catches only
   `KeyboardInterrupt`; ~11 AI call sites re-raise; `flow.py` has two `try`
   blocks. One transient API/network failure ends a session with a traceback.
   Degrade tutor/reviewer to "unavailable" and keep the loop alive; test with a
   backend that raises.
6. **The prereq gate degrades to "content exhausted."** `_prereqs_satisfied`
   asks whether a prerequisite has an unsolved *curated* ladder problem left, so
   an empty bank satisfies it trivially — 12 of 18 groups report OPEN with only
   7 problems solved. Either gate on roadmap coverage with uncurated rows
   counted, or document the degradation; today the status line promises
   "prerequisites gated."
7. **The curator prompt still enumerates the pre-v0.10 taxonomy.**
   `CURATOR_SYSTEM` lists `dynamic_programming`, `math`, `graph` (9 old
   patterns) while `curator.validate` enforces the 18 NeetCode slugs — so
   `dojo curate` cannot curate any DP/Math/Geometry problem at all. `dojo fetch`
   survives only because it passes a pattern hint. Fix the prompt's enum.
8. **Mock and live reviews are indistinguishable in the learner model.**
   Nothing records which backend produced a review; a `DOJO_AI_BACKEND=mock`
   row sits in `attempts` next to live ones (attempt 2 in the live DB is canned
   mock text, and it lacks `complexity_reasoning`/`reflection_feedback`). Add a
   backend/model provenance column before any analysis of the model.
9. **`duration_seconds` measures wall-clock since session start** (one sample:
   84,773 s ≈ 23.5 h across a closed laptop) and is consumed by nothing. Either
   measure real solve time or document it as a session span.
10. **MockBackend keys canned branches on system-prompt substrings**, so a test
    fixture constrains production prompt wording — `TEACHER_SYSTEM` is forbidden
    from containing "tutor"/"discussion", and the discussion branch has already
    silently died once. Replace with an explicit role argument on the backend
    protocol, and delete the `or len(tutor) > 0` escape hatch at
    `tests/test_flow.py:435` (it makes the assertion unfalsifiable).
11. **The CLI command layer is untested.** 11 of 15 `_cmd_*` functions are never
    invoked by the suite, and no test drives `main()` into a real `run_day`.
    Add one `main(["day", slug])` smoke test plus tests for
    `show`/`history`/`check`/`warmup`/`report --fix`.
12. **Content, not code: 121 of 150 ladder problems are landed but uncurated**
    (29 curated + ladder-tagged), so the ladder and the prereq gate operate over
    a 29-problem subset. The "126 still to fetch" note is really "121 still to
    curate."
13. **`problems.source` is a dead column** — always `'seed'`, even for the 155
    fetched/lc-numbered rows, so provenance is unrecoverable.

## v0.13 Stage 0 — shipped (the trust subset)

See [v0.13](v0.13.md) for the full record. In one line each: the leak audit fails
**closed** (an unreadable rating discards the hint and says so); the judge
captures file descriptor 1 and never raises (a malformed protocol is a verdict,
not a traceback); output is bounded and process groups are killed
(`dojo/proc.py`); a case that raised is `status="error"`, not `wrong_answer`; an
empty case list is refused; every AI call runs behind `dojo.guard`; `dojo report
--fix` can no longer delete a row attempts reference; the warm-up grade is one
transaction and cannot be applied twice; `dojo curate`'s prompt enum comes from
the taxonomy it is validated against; `static.analyze` cannot raise and keeps its
ruff cache out of the repo; the trend table counts solves as solves; templates
that would not compile are refused loudly; the timing flake is gone (the probe's
measurement is injected in tests, never its verdict); and the suite now drives
`cli.main` end to end against a sandboxed DB and workbench.

## v0.11 work — shipped

- Warm-up picks rotate (per-problem `MAX(submitted_at)` aggregation).
- The recall grade is persisted (`attempts.recall_grade`); per-pattern recall
  curves are now reconstructible, which unblocks item 5 below.
- The profiler measures time with no tracer running, reports the range it can
  support, and no longer flags a claim it cannot rule out (8/15 false flags →
  0/15 on the stored solutions).
- Multi-parameter complexity claims are compared, not silently skipped.
- `quit` records nothing: an attempt row exists iff the student submitted.

## Proposals from the v0.8 design audit

1. **Judge ground-truth anchor + false-failure banner.** For LeetCode-fetched
   problems, validate the AI oracle against LeetCode's own judge once at
   curation time and store the verdict in the proposal provenance (dual-oracle
   agreement stays, but as a filter before the real check). In `_submit`, a
   distinct message when a submission fails only generated/oracle cases (visible
   cases pass) — "this could be a curation bug — `dojo report` audits it" —
   instead of a plain ✗. Converts the worst failure mode from silent trust loss
   into a visible, fixable event.
2. **Warm-up rotation floor.** → superseded by the v0.11 rotation fix (the
   rotation never happened at all); only the *variant* idea below remains.
3. **Streak + reminder.** Status line shows consecutive practice days; the setup
   wizard offers a daily cron/launchd entry with the same consent UX as the PATH
   wrapper. The actual adoption risk is the habit, not the loop's interior.
4. **Consolidate `profile` into `history`** (near-duplicate commands; keep
   `progress` for patterns, `show <id>` for detail) and hold the session command
   list ≤7. ✅ shipped in v0.9 — `profile` is now a hidden alias of `history`.
5. **Reviewer calibration in `dojo progress`.** Reviewer scores vs. subsequent
   warm-up grades per pattern, plus hint-count correlation — an audit loop for
   the *reviewer*, mirroring what `report` does for the *curator*. Unblocked by
   the v0.11 grade-persistence fix.
6. **Learner-model steering.** Stall detection (tier at abandon, hint counts)
   feeding problem selection and the proactive learn offer. Note the current
   offer fires only on `unstudied(pattern)` — a pattern you have *attempted and
   failed* is "studied" by definition, so the offer is structurally blind to the
   strongest signal. Trigger on repeated abandonment instead.
7. **Write-up.** The never-solve-as-architecture idea, the honesty contract, and
   the grader self-audit loop are worth a public write-up; the design docs are
   the second-most-valuable artifact.
8. **Terminal rendering polish.** ✅ shipped in v0.10.3 (the markdown flip).

## Backlog (unchanged)

- TUI polish (Textual) — only if the CLI loop proves insufficient.
- Two-machine sync.
- Warm-up problem variants (transfer, not recognition — see docs/retention.md).
- A web UI — only if the CLI proves insufficient, never first.
