# Audit — dojo at v0.12

*Prepared 2026-09-19 against `465842c` (v0.12.1 + 23 registered references).
Read-only: nothing in `src/`, `tests/`, or the data files was changed. Findings
carry an evidence tag — **[X]** executed and observed, **[R]** read from the
source, **[S]** suspected (reasoned from verified mechanisms, not run).*

Scope: the whole repository — `src/dojo/` (~10k LOC across 32 modules), the test
suite (6,642 LOC, 326 tests), the seed corpus (179 parseable problem files), the
live database (182 `problems`, 35 `attempts`, 3 `pattern_cards`, 1 user), the
debug log (171 JSONL events), and every doc. It re-checks the 13 findings the
v0.11 audit left in [roadmap/next.md](../roadmap/next.md) and adds whatever a
first-principles read turns up. It does **not** judge pedagogy — that needs a
learner, not a reader.

| Band | Count | Meaning |
|---|---|---|
| **S1** trust and durability | 12 | a recorded fact is wrong, or a session dies |
| **S2** correctness and lost data | 25 | wrong or lost data on a narrower path |
| **S3** learner-model fidelity | 11 | the model records less than it claims |
| **S4** ergonomics and product gaps | 8 | friction, and the two feature requests |
| **S5** content, identity, hygiene | 10 | the bank, the tests, the docs, the versions |

**Fix first:** S1.1 (leak audit fails open), S1.2 (an `os.write` to fd 1 crashes
the session), S1.6 (`report --fix` can delete a problem row attempts point at),
S1.7 (a crash double-counts a card grade), S1.8 (a runaway `print` OOMs the
machine *or dojo*), and the flake in S5.6. Everything else is either cheap
hygiene or a product decision.

The verdict in one paragraph: dojo's *ideas* are stronger than its *plumbing*.
The never-solve boundary, the evidence-never-verdict measurement contract, and
the machine-verified curator gate are genuinely good design, and the
documentation culture that records why each of them exists is better than most
production repos. What is weak is the session layer and the trust seams around
the AI: the tutor's leak audit still fails **open** (a complete solution is
delivered when the auditor misbehaves — four ways, all reproduced), a `print` to
file descriptor 1 in student code still kills the session with a traceback, and
the artifact the AI reads is the raw workbench file, chrome and all. None of
these are hard to fix; all three get worse, not better, as dojo grows from one
curriculum to three.

---

## 1. What the project does well

Ordered by how much each one is worth preserving. Each entry says *what* and
*why it matters*, because the reason is the part that has to survive a rewrite.

1. **Never-solve as an architectural property, not a prompt sentence.**
   `docs/architecture.md:12-20` states the rule and the code honors it: oracles
   live in exactly one module (`judge/registry.py`), the tutor's context is
   statement + code + tier + history (`tutor/prompts.py:153-173`), and
   `tests/test_never_solve.py` pins the boundary mechanically. The one narrowing
   (the teacher may show topic-canonical code) is documented, justified, and
   scoped. This is the project's best idea and its least negotiable one: a tutor
   that can solve is a tutor nobody learns from.

2. **The honesty contract in the measurement layer.** v0.11/v0.12 removed a
   feature (`fit.py`) because it could not answer the question it was built to
   answer, and wrote down why: `roadmap/v0.12.md:1-12`,
   `docs/grading.md`, AGENTS.md rule 7. The paired-reference probe, the
   three-valued `complexity.compare` (agree / disagree / incomparable), and the
   rule that an unresolved measurement *never* reddens a claim
   (`session/flow.py:198-234`) are the shape of a tool that would rather say
   "I don't know" than flatter the user. Very few learning tools do this.

3. **AI proposes, the machine disposes.** The curator's oracle is verified
   against generated cases before it is applied; a reference is admitted only if
   it agrees with the brute-force oracle everywhere the oracle can run
   (`curator/curator.py`, `judge/registry.py`); `dojo report` audits the audit.
   Machine-checkable artifacts are gated; uncheckable ones (pedagogy) are
   *labelled* as uncheckable rather than silently trusted.

4. **Per-case verdict modes, and the isolation that makes them honest.**
   `sorted` / `rounded:n` / `approx:t` / `predicate` / `ops`
   (`judge/runner.py:1-16`) is a small, complete vocabulary that matches how
   interview answers actually differ. Strict JSON equality is deliberate and
   type-exact — `check_equal(True, 1)` and `check_equal(1.0, 1)` both return
   False **[X]** — which is the correct default for a grader and a trap most
   implementations fall into.

5. **The debug log.** `data/logs/dojo.log` records every live AI exchange —
   system prompt, user prompt, the raw response *before* parsing, latency,
   transport errors (never the key). It is the reason this audit can say
   "the reviewer complained about the shebang in 15 of 18 reviews" instead of
   "the reviewer complains a lot" **[X]**. A tool built on a non-deterministic
   dependency needs exactly this, and almost none have it.

6. **Test discipline that matches the rules.** 326 tests, 18 seconds, fully
   offline, deterministic, mock-backed (`make test` **[X]**). No wall-clock
   assertions on complexity classes (rule 5), injectable HTTP transport and
   update runner, prompt-versioned mocks, `FakeConsole` with an action hook that
   simulates editing the workbench mid-session (`tests/conftest.py:26-51`).

7. **The documentation culture.** `docs/` holds technical truth, `roadmap/`
   holds staged plans *with their post-mortems* (v0.11 documents its own
   ~20x-too-small FSRS increment; v0.12 documents the deleted fit), and
   `AGENTS.md` carries the operational memory that keeps an AI contributor from
   re-breaking things it already broke once. Few repos of this size can be
   audited by a stranger in an afternoon; this one can.

8. **The attempt row as the learner model.** Hint count *and* transcript,
   self-reported vs. measured complexity, the review, the reflection, the static
   analysis, the scale-probe record, the discussion transcript, the recall grade
   — all on one row (`db.py:40-65`). The v0.11 decision that "an attempt exists
   iff the student submitted" is a semantic fix, not a cosmetic one, and it is
   written down as such.

9. **Additive-only migrations and "user data is real" as a hard rule**
   (AGENTS.md rule 4, `db.py:108-145`). `ensure_seeded` upserts and never
   deletes; `retire_state` leaves the workbench file alone. The tool is allowed
   to be wrong about a problem, but not to lose a person's history.

10. **Terminal ergonomics taken seriously.** The virtual-text command hint, the
    typo guard before a consequential command, the double-check gate on
    complexity claims, `patch_stdout` around every print between prompts, and
    the `default=None` post-mortem (`terminal.py:50-95`, AGENTS.md). Unglamorous
    and directly responsible for whether the daily loop gets used.

11. **The workbench lives outside the repo, with self-healing IDE config.**
    `~/.local/share/dojo/workbench` + generated `.vscode/`/`.zed/` + a folder
    launch (`editor.py:134-189`) is the right call: editor and debugger tooling
    can never collide with `git`. (The story is incomplete — see F1 below — but
    the foundation is right.)

12. **Sane secrets and env handling.** Key from env → gitignored `.env` →
    prompt, never logged, `--skip-key` for scripted installs, `mock` backend for
    everything offline (`config.py:60-84`, `setup.py`).

---

## 2. What needs improvement

Severity is about *cost when it goes wrong*, not about how hard the fix is.
S1 = breaks trust in a recorded fact or kills a session; S2 = wrong or lost
data in a narrower path; S3 = the learner model records less than it claims;
S4 = ergonomics and product gaps; S5 = content and repo hygiene.

### S1 — trust and durability

**S1.1 The tutor's leak audit fails open — a full solution is delivered.**
`tutor/tutor.py:103-108`:

```python
def _audit(backend, text) -> int:
    leak = backend.chat_json(LEAK_CHECK_SYSTEM, build_leak_prompt(text, 0))
    try:
        return int(leak.get("rating", 1))
    except (TypeError, ValueError):
        return 1          # 1 == "clean" == deliver it
```

Every failure mode of the auditor collapses to "safe": a non-JSON response
(`{"error": ...}`), a missing `rating`, a string rating, a `None` rating. All
four were reproduced against a leaking tutor response **[X]** — the response
containing a complete `two_sum` implementation was delivered in 4/4 cases, with
`leak_rating=1`. `roadmap/next.md` listed this as open finding #1 in the v0.11
audit and it is still open. The never-solve rule is the project's headline
promise, and its last line of defense is fail-open. Fix: fail **closed** (a
failed audit is a discarded hint plus a visible "couldn't verify this one — try
rephrasing"), keep the retry, and add one test per failure mode.

**S1.2 Student code that writes to file descriptor 1 kills the session.**
`judge/runner.py:48-59` redirects `sys.stdout` only. `os.write(1, ...)`,
`os.system(...)`, or any subprocess inherits the real fd 1, which *is* the
protocol channel, so the parent's `json.loads(proc.stdout)` at `runner.py:189`
raises `json.JSONDecodeError` **out of `run_cases`** **[X]**. `flow._submit`
calls it without a guard (`flow.py:657`) and `cli.main` catches only
`KeyboardInterrupt` (`cli.py:1477-1479`), so the user sees a traceback and loses
the session. This is the same bug class as the v0.10.1 `print` crash that
`isolated()` was written to fix (next.md #3) — half-fixed: Python-level stdout is
captured, the file descriptor is not. Fix: capture at the fd level
(`os.dup2` onto a temp file for the duration of the harness), and make
`run_cases` never raise — a malformed protocol is `status="error"` with the
offending text attached.

**S1.3 A submit can be graded with zero cases.** `run_cases` returns
`JudgeReport(status="correct")` when `cases == []` (`runner.py:156-157`), and
`_build_cases` returns `[]` when a problem has no visible tests and no
`@judge_case` generator (`flow.py:111-131`). The CLI guard is
`if not problem["function_name"] or not problem["visible_tests"]`
(`flow.py:1000`) — which tests the truthiness of the *JSON string*, so a stored
`"[]"` passes the guard and the student is told "✓ All 0 cases passed" and
recorded as `correct` **[X]** (mechanism reproduced; no current problem triggers
it — all 31 curated rows have both visible tests and a generator). Latent, but
it is a free pass in the one place there must never be one. Fix: validate
non-empty cases in `run_cases` and non-empty `visible_tests` by parsed value,
not by string truthiness.

**S1.4 `dojo curate` is broken for 11 of the 18 pattern groups.**
`curator/prompts.py:15-17` instructs the model that `pattern` is one of
`arrays_and_hashing, stack, two_pointers, trees, heap, binary_search, greedy,
dynamic_programming, math` — the pre-v0.10 taxonomy. `curator/curator.py:61-64`
validates against `patterns.PATTERNS`, the 18 NeetCode slugs. So a DP or math
statement gets `dynamic_programming` from the model and is rejected by
validation, and a graph/linked-list/trie/backtracking/intervals/bit-manipulation
statement can only be *mis-bucketed* into one of the nine allowed values
(silently landing in the wrong ladder). `dojo fetch` survives only because it
passes a pattern *hint* in the user prompt. next.md #7, still open. Fix: the
prompt's enum must be generated from `patterns.PATTERNS` — a hardcoded taxonomy
duplicated in a prompt is a drift generator.

**S1.5 One transient API failure ends the session with a traceback.**
~11 AI call sites re-raise; `flow.py` guards two of them; `cli.main` catches
only `KeyboardInterrupt`. A network blip during a hint, a review, or the
curator produces a stack trace at the exact moment the learner is invested
(next.md #5, open). The reviewer path has a graceful non-JSON fallback
(`flow.py:716-718`) — that shape should be the rule for *every* AI call, not the
exception.

**S1.6 `dojo report <slug> --fix` can delete a problem row that attempts point
at.** On a failed verification gate, `curator.apply` rolls back by restoring the
file, re-seeding, and then calling `_delete_problem_row`
(`curator/curator.py:731-738`). The helper's docstring states its premise —
*"the slug is guaranteed fresh, so no attempts can reference it"*
(`curator.py:273-275`) — and that premise is exactly false for the `overwrite`
path: the "already curated" guards are skipped when `overwrite=True`
(`curator.py:646-651`), which is the *only* way `dojo report --fix` calls it
(`cli.py:1136`). With foreign keys on (they are, `db.py:103`) the `DELETE`
raises `IntegrityError`, which **replaces** the intended
`CuratorError("verification gate failed; rolled back.")` on the next line — so
the student sees a foreign-key traceback instead of a rollback, i.e. a wrong
trail. With FKs off, the row goes away while its attempts remain, and because
every history and ladder query INNER JOINs `problems`, those attempts disappear
from `dojo history` and the solved set. [R] Fix: make the delete conditional on
the apply having *created* the row (pass `created: bool`, or check
`SELECT 1 FROM attempts WHERE problem_id = ?` first).

**S1.7 A warm-up recall grade can be applied to the card twice.** The card
update and the attempt's grade are two separate transactions on one connection:
`record_grade` commits (`scheduler.py:229`), then `recall_grade` is written and
committed (`flow.py:1190-1194`), and only then is the state file retired
(`flow.py:1196`). A crash in that window leaves a live state file whose
`attempt_id` is set; the next warm-up for the same pattern (guaranteed to pick
the same problem when it is the pattern's only solved one) resumes that state,
and a second submit calls `record_grade` again — `reps +2`, `lapses +2` on a
lapse, `recall_grade` overwritten, and the crashed attempt's code and timestamp
overwritten in place by `_record_submit`'s UPDATE branch (`flow.py:630-635`).
`record_grade` is a read-modify-write with no link to the attempt that justified
it (`scheduler.py:207-229`) — nothing anywhere asserts "this attempt has not
already graded this card". [R] Fix: one transaction for card + attempt, and a
guard on `attempts.recall_grade IS NULL`.

**S1.8 A runaway `print` can OOM the machine — or dojo itself.** The judge's
`PRINT_CAP` is applied *after* the output is materialized in an `io.StringIO`
(`runner.py:57`), so it bounds nothing: an infinite print loop drove the child to
~1.9 GB RSS in three seconds and would reach ~6 GB by the 10 s timeout **[X]**.
Worse is the probe: user prints are deliberately routed to stderr
(`probe.py:96` `sys.stdout = sys.stderr`) and the parent captures stderr
unbounded (`probe.py:273` `capture_output=True`), so dojo's *own* RSS went
21 MB → ~1.75 GB in two seconds, against a 20 s timeout **[X]**. The same
unbounded capture exists for stderr in the judge (`runner.py:167`). Fix: cap on
the child side (a `sys.stdout` proxy that raises or truncates past N bytes) and
stream/discard the parent's stderr beyond a fixed prefix.

**S1.9 A timeout leaves the grandchildren running.** `subprocess.run(...,
timeout=...)` kills only the direct child (`runner.py:164-172`,
`probe.py:263-278`) — no `start_new_session`, no `killpg`, no NPROC limit. A
solution that spawns a background `sleep 77.5` still had it alive after the run
was reported `timed_out` **[X]**; a fork bomb would outlive dojo. Fix:
`start_new_session=True` + `os.killpg` in the timeout handler, plus
`resource.setrlimit` for CPU/address space in the child.

**S1.10 The judge mis-grades predicate problems when the solution mutates its
arguments.** Unlike the probe (which deepcopies per call), the judge passes the
student's own args to the checker: `CHECKERS[case["predicate"]](solution, got,
case["args"])` (`runner.py:90`). Reproduced in both directions **[X]**: a correct
`find_a_peak` that returns index 0 is `correct` when it does not mutate and
`wrong_answer` (with `error=None`, so the failure table prints expected == got)
when it does `nums.sort()` first; and `_k_closest_valid` returns `True` for
garbage output when the student rewrote `points[:]`, because the checker
recomputes its threshold from the mutated list
(`judge/registry.py:777-792`). Fix: deepcopy per case in the harness, exactly as
the probe does.

**S1.11 The probe can claim a class the ratio does not support.** Every growth
branch writes `reference_class=declared_class` (`profiler/growth.py:170`, `:197`,
`:224`, `:236`), `steps` is an index difference against that same declared class
(`growth.py:232`), and the note reads "than the reference (O(n))"
(`growth.py:248-250`) — but the reference's *own* class is never measured, and
references are gated for correctness only. So a student whose O(n²) code matches
a reference that is also O(n²) while the problem's declared class is O(n) is
told *"grows like the reference — consistent with O(n)"*, verdict `MATCHES`,
`student_class=O(n)` **[X]**. That is the v0.11/v0.12 honesty rule ("never claim
a class the ratio does not support") broken by construction, not by noise. Fix:
carry the reference's class as curated, gate-checked data, or measure it with the
same estimator and report the assumption in the note and in `dojo show`.

**S1.12 A student solution can rewrite its own verdict.** The student's module is
executed *inside* the harness process, so `sys.modules["__main__"].check_equal =
lambda *a, **k: True` — or patching `CHECKERS`, or `dojo.judge.compare`'s
globals — makes `run_cases` report `correct` for a function returning 12345
**[X]**. In a two-person private tool this is self-deception rather than a
security hole, so the right response is a documented decision, not a sandbox:
say so in `docs/grading.md`, and (cheap) re-import the comparators *after*
loading the solution module, or hold the comparison in the parent. Note the same
property exists in the curator's in-process gate (`curator.py:364`), where the
executed code is model-generated.

### S2 — correctness and lost data in narrower paths

**S2.10 The template stub advertises a command that no longer exists.** Every
blank workbench file says *"Use `dojo check` / `dojo hint` from a second
terminal"* (`flow.py:63-65`). `hint` was removed in v0.10.1 (any bare input is a
question) and "from a second terminal" stopped being true when the prompt became
non-blocking. This is the first text a learner reads, in the file they will look
at for an hour.

**S2.1 The original submission is destroyed by the next submit or polish.**
`attempts` carries a single `code` column (`db.py:45`). `_record_submit`
`UPDATE`s it on every later submit in the session (`flow.py:630-635`) and
`_polish` does the same (`flow.py:847-856`), keeping only a `polished` counter
(`db.py:61`). So a student who submits, iterates, and polishes has exactly one
surviving artifact: the last version. The original — the thing the review, the
complexity claims, and the first scale probe actually graded — is gone. This is
the user's report #1, confirmed by reading **[R]**; the schema is the cause and
the fix belongs there (see v0.13 §A), not in the CLI.

**S2.2 Warm-up crash recovery silently wipes recovered code.**
`run_warmups` force-writes a blank template *before* calling `run_day`
(`flow.py:1249`), but `run_day` decides whether to overwrite from the state file
(`flow.py:1010`, `:1026`) and correctly keeps the file when a crashed session is
being resumed. The blanket `force=True` already clobbered it. Net effect: crash
recovery works for solves and is a no-op for warm-ups **[R]** — the student's
in-progress recall attempt is replaced by a stub, with no message. Fix: the
template decision lives in exactly one place (`run_day`), keyed on
`is_new_session`.

**S2.3 A failed submit records code but no hints and no duration.**
The insert in `_record_submit` writes `code`, `status`, `started_at`,
`submitted_at` (`flow.py:611-629`) and returns; `hint_count`, `hints`, and
`duration_seconds` are only written by the *successful* submit's UPDATE
(`flow.py:722-750`). So "failed, used four hints, quit" stores an attempt with
`hint_count=0`, `hints=NULL`, `duration_seconds=NULL` **[R]** — precisely the
row the learner model most needs when it asks "what does struggle look like?".
Fix: write every signal the session owns on insert, and update it on each
submit.

**S2.4 A failed re-review wipes the review that already existed.**
`_polish` sets `review_json = {}` when the re-review returns non-JSON
(`flow.py:841-845`), then writes `dumps_json(review_json) if review_json else
None` (`flow.py:866`) — i.e. the stored review becomes NULL. Same shape at
`flow.py:716-718` for the first submit (there it is harmless, the row is new).
Fix: keep the previous review on a failed re-review and say so.

**S2.5 Case-level errors are reported as `wrong_answer`.**
`status` is computed from the pass count alone (`runner.py:202-203`), so a case
that raised (`ValueError: boom` **[X]**) is indistinguishable from a wrong
answer, and `error` — a status the type comment advertises
(`runner.py:139`) — is unreachable for case errors. next.md #4, still open. It
matters because `_submit` prints `— status: error` only for non-`wrong_answer`,
and because "my code crashed" and "my logic is wrong" are different coaching
problems. Fix: `error` when any case carried an exception; keep `wrong_answer`
for pure mismatches.

**S2.6 A timeout discards every per-case result.** `run_cases` returns
`JudgeReport(status="timed_out", results=[])` (`runner.py:171-172`), so a single
hanging case hides the 29 that passed and the one that hung. Fix: run cases in
the child with a per-case budget, or at minimum report which case index was
being executed when the wall clock expired.

**S2.7 A statement containing `"""`, a trailing quote, or a backslash produces a
file that does not parse.** `_render_template` interpolates the statement
directly into a module docstring (`flow.py:76`). Reproduced **[X]**: a statement
containing `"""`, one ending in `"`, and one with `\sum`/`\d` all yield
`SyntaxError` — and the student's first `check`/`submit` then fails as a
"harness error" rather than as a curation problem. Fix: emit the statement with
`repr()`-safe quoting (or as a comment block), and validate the rendered
template compiles before writing it (`compile(src, "<template>", "exec")`).

**S2.8 `dojo check` / `dojo report` can target the wrong problem.**
Both pick `sorted(WORKBENCH_DIR.glob("*.state.json"))[0]`
(`cli.py:600-602`, `cli.py:1088-1093`) — the alphabetically first live session,
not the most recently touched. With several crashed sessions around (the only
resumption path, by design), `dojo check` can silently test a file the student
is not looking at. Fix: most-recently-modified state file, and print which slug
was chosen.

**S2.9 `_discuss` assumes the attempt row exists.** `conn.execute(...).fetchone()["discussion"]`
(`flow.py:878-883`) raises `TypeError: 'NoneType' object is not subscriptable`
if the row is gone **[X]**. Only reachable through a stale state file or a
deleted row today, but the post-solve loop is about to gain commands; a guard
plus a graceful "this attempt is no longer in the database" is cheap.

**S2.11 The due-card query has no tie-break, and backfill makes every card tie.**
`due_cards` orders by `datetime(due_at) ASC` only (`scheduler.py:239-257`), and
`backfill_cards` gives every card `due = now()` at second resolution
(`scheduler.py:433-445`) — so after a fresh setup all backfilled cards share one
identical `due_at` and `run_warmups(limit=2)` picks an arbitrary subset in
unspecified order, ignoring roadmap priority. Related: `defer`
(`scheduler.py:448-455`) moves `due_at` forward and records nothing, so a card
whose pattern has no re-solvable problem loops due → defer → due forever while
`due_now_count` keeps advertising it (`flow.py:1241-1248`). [R]

**S2.12 `warmup_problem` reintroduces the v0.11 rotation bug for NULL rows.**
The per-problem `MAX(a.submitted_at)` aggregation is the v0.11 fix, but `MAX()`
is a raw *string* max with no `datetime()` (`scheduler.py:260-284`) — the exact
hazard `due_cards` explicitly defends against — and a NULL sorts first in ASC,
so a problem whose only correct attempt has `submitted_at IS NULL` is pinned as
the warm-up forever. There is no `submitted_at IS NOT NULL` filter. [R]

**S2.13 Which row a ladder rung resolves to is arbitrary.** `_problem_by_lc` is
`LIMIT 1` with no `ORDER BY` (`scheduler.py:344-353`) and `problems.lc_number`
has no UNIQUE index (`db.py:36`); `_tag_lc_number` guards only on
`lc_number IS NULL` (`cli.py:850-860`) and its own comment acknowledges two slugs
can own one number (`cli.py:880-883`). With a duplicate, `dojo` can serve a
different row than `dojo roadmap` reports, and a rebuilt DB can differ from an
incremental one. Three concrete cases exist in the live DB: `implement-trie`
(lc 208), `lowest-common-ancestor-of-a-bst` (lc 235) and `pow-x-n` (lc 50) hold
ladder numbers, have **no seed file**, and are uncurated — while the files that
do exist (`implement-trie-prefix-tree.py`, `powx-n.py`) have `lc_number = NULL`
and nothing in the codebase will ever set it (only `fetch` tags numbers). Those
three rungs are permanently unreachable without manual DB surgery. [X]

**S2.14 `review_trends` counts warm-up re-solves as solves.** The query filters
`status='correct' AND review IS NOT NULL` with no `kind` filter
(`db.py:331-344`), and warm-ups *do* store a full review (`flow.py:699-751`
suppresses only the reflection). So `dojo progress`'s "solves" column and its
recency-weighted rubric trend mix first solves with hint-free recall re-solves —
and `tests/test_trends.py` only ever inserts `kind='solve'`, so nothing pins it.
[R]

**S2.15 Connections are never closed, and there is no WAL.** `with connect(...)`
appears ~25 times but `sqlite3.Connection.__exit__` commits/rolls back — it does
*not* close; the only `conn.close()` in the tree is inside `init_db`
(`db.py:154`). `dojo fetch --all` opens three connections per problem inside its
loop (`cli.py:894`, `:901`, `:914`). `connect()` sets no `journal_mode=WAL`, no
`busy_timeout`, and no explicit `timeout=` (`db.py:99-105`), while
`bank.ensure_seeded` writes the whole bank in one transaction at *every* CLI
entry and `run_day` holds a connection for an entire interactive session — the
exact pattern WAL exists for, on a machine that is explicitly shared by two
users. [R]

**S2.16 Migrations have no version and no coverage for two tables.** Every
`ADD COLUMN` ever committed is handled (`db.py:118-143`), and no `DROP`/type
change exists — the additive discipline holds. But: there is no
`schema_version`/`PRAGMA user_version` anywhere, so nothing can assert that two
DBs converged and a one-time *data* migration has nowhere to live; the
fresh-DB guard checks only for the `attempts` table (`db.py:112-117`) although
its comment claims "fresh (or partial)", so a DB with `attempts` but without
`problems` is never repaired (and `executescript(SCHEMA)` would be safe —
every statement is `IF NOT EXISTS`); and `pattern_cards` and `users` get no
migration coverage at all, so any future column on them exists only on fresh
DBs. The snapshot of existing columns is read once per `migrate()`, so two
concurrent starts can both see a column missing and one raises
`duplicate column name`. [R]

**S2.17 The per-case handler does not cover the `expected` lookup.**
`runner.py:73` reads `case["expected"]` *outside* the `try` that starts on line
75, so one malformed case kills the harness and every other case with it — one
synthetic `label="harness"` row, status `error` **[X]**. Not reachable from
today's corpus (every visible test carries `expected`, and only `sorted` ×17 and
`approx:0.0001` ×3 are in use), but `run_cases` is a public export and nothing
validates the case contract.

**S2.18 Prints are discarded exactly when they are needed.** `isolated` returns
`call(), buffer.getvalue()[:PRINT_CAP]` (`runner.py:57`) — if the call raises,
the buffer is gone — and the handler hard-codes `"printed": ""`
(`runner.py:114`). Every *crashing* case therefore shows no output, which is the
opposite of the v0.10.7 rationale ("prints are debugging statements, and `check`
is the debugging loop"). Module-level prints are also discarded on success: the
`isolated(lambda: spec.loader.exec_module(solution))` return value at
`runner.py:68` is dropped.

**S2.19 `_median_run` silently drops errored repeats.** `probe.py:299` keeps only
`r.ok` runs. A failure on repeat ≥ 2 at n=100 was reported `ok=True` with a time
and spread 0.0, and the ascent continued; the error only surfaced at n=200 where
it was persistent **[X]**. That contradicts the module's own headline
("Failure is a result… it used to be swallowed", `probe.py:9-11`) for any
non-deterministic failure.

**S2.20 `has_reference` means "a Target was passed", not "a comparison was
possible".** `probe.py:336` sets it from `reference is not None`, `flow.py:504`
passes it through, and `growth.verdict` has no reference-failure input — so a
reference that dies at n=3200 still leaves five usable points and the student
gets a class named from below the break, with the reference failure reported
separately in the UI (`flow.py:285-291`).

**S2.21 The interleave order is fixed, and the identical-code control measures
below 1.0.** The probe runs student-then-reference at every repeat and size
(`probe.py:341-345`) with no swap; the control documented in
`docs/grading.md` and `tests/test_probe.py` puts *identical* code at 0.87–1.04.
A sub-1.0 median for identical code is what a positional advantage looks like
(first process gets the boost clock / warm cache, second runs hot). A constant
offset cancels in the trend, but an offset that grows with n does not. Cheap
check: swap the order on alternate repeats and assert the ratio moves toward 1.0.
[S]

**S2.22 The probe carries a third canonicalization, already drifted from
`compare.canonical`.** `probe.py:71-85` sorts dicts with
`sorted(value.items())` (raw Python ordering) while `compare.py:24-25` sorts by a
JSON key. With `compare="sorted"` and an output of `{1: 'a', 'b': 2}` the digest
raises `TypeError`; because that happens on the `finally`-print path the JSON
still prints, `run_one` sees non-empty stdout and reports `ok=True,
digest=None` — so the output comparison silently disappears **[X]** (and
`run_one` never checks `proc.returncode` either). One canonicalizer, imported by
both.

**S2.23 The space axis is asymmetric and easy to disable by accident.** A
`MemoryError` in the space call is swallowed into `peak=None`
(`probe.py:142-143`) while the same exception in the timed call is fatal; a
student module that calls `tracemalloc.start()` at import makes the harness's own
`start()` a no-op (peaks measured against the student's baseline), and
`tracemalloc.stop()` inside the function yields `peak=0`, which
`if not stu.peak` (`probe.py:197`) turns into "no ratio" — indistinguishable from
"not measured" **[X]**.

**S2.24 `probe_max_n` can produce a degenerate ladder.** `ladder(32)` returns
`[0, 1, 2, 4, 8, 16, 32]` — n=0 is a real input, so a reference that divides by n
leaves one dead point — and `ladder(1)` returns `[0, 0, 0, 0, 0, 0, 1]` **[X]**.
`probe_max_n` is a documented per-problem override (`bank.py:49`,
`flow.py:461`), so this is one curation typo away. Fix: clamp the ladder to a
minimum of 2 points ≥ 2 and de-duplicate.

**S2.25 `static.analyze` can raise, contradicting its own contract.** Its
docstring says "Never raises" (`static.py:49`), but
`source = code_path.read_text()` (`static.py:51`) sits outside both `try` blocks:
a missing file → `FileNotFoundError`, a non-UTF-8 file → `UnicodeDecodeError`
**[X]** — and `_check` calls it *after* a successful judge run (`flow.py:338`),
so a decode error there loses a passing submit. Its side effect is also visible
in the repo: ruff is spawned without `--no-cache`/`--cache-dir`, so it writes
`.ruff_cache/` into the process cwd — which is why that directory exists in the
repo root and why `make test` mutates the working tree.

### S3 — the learner model records less than it claims

**S3.1 Mock and live attempts are indistinguishable.** No `backend`/`model`
column exists, so the live DB mixes canned reviews with real ones (next.md #8) —
attempt 2 is mock text and lacks the v0.10.11 rubric dimensions. Any future
analysis of "does the reviewer track the warm-up grades?" (next.md proposal #5)
starts by hand-filtering. Fix: `ai_provenance` JSON (backend, model, prompt
version) on the attempt row.

**S3.2 `duration_seconds` is wall-clock since session start** (`flow.py:737`) and
therefore includes laptop sleep (one stored row: 84,773 s ≈ 23.5 h; next.md #9).
Nothing consumes it. Either measure real solve time (last edit? `check`
first-pass time?) or rename and document it as a session span.

**S3.3 Dead columns and dead vocabularies accumulate.** `measured_time_r2` /
`measured_space_r2` are written as NULL by both submit and polish and still
render as an `r²` column in `dojo history` (`cli.py:624`, `:638`).
`problems.source` is always `'seed'` even for the 155 fetched rows
(next.md #13). `MAJOR_VERSION = "0.10"` while the stage is v0.12 and
`pyproject.toml` says `version = "0.1.0"` — three version notions, none
authoritative.

**S3.4 The FSRS card unit is coarse.** One card per `(user, pattern)`
(`db.py:67-80`): "stack" is a single memory for seven heterogeneous problems
(two-pointers-of-a-string vs. monotonic-stack vs. largest-rectangle). The
scheduler can therefore record "stack: stable, due in 21 days" when what is
actually stable is *valid parentheses* and what is fragile is *largest rectangle
in histogram*. The data to know better already exists on the attempt rows — the
card is just aggregated too early. (docs/retention.md is honest about the
aggregation; the cost is invisible in `dojo progress`, which shows one row per
pattern.)

**S3.5 The proactive learn offer is structurally blind to the strongest signal.**
`unstudied()` (`db.py:280-284`) is true only when there is no learn session *and*
no attempt — so a pattern attempted three times and failed three times is
"studied" and never offered. next.md proposal #6 identified this; it is still
true.

**S3.6 `_prereqs_satisfied` degrades into "content exhausted".** The gate asks
whether a prerequisite still has an unsolved *curated* ladder problem, so an
empty bank satisfies it trivially (next.md #6 — 12 of 18 groups report as open
with 7 problems solved), while `_cmd_day` prints "roadmap order, prerequisites
gated". Either gate on roadmap coverage with uncurated rows counted, or stop
promising the gate in the status line.

**S3.7 A learner-model bug fixed in v0.11 left its evidence behind.** The live
DB still holds 8 `solve/unsolved` and 3 `warmup/unsolved` rows **[X]** — status
values the current code cannot write (`_record_submit` stores the judge's
verdict). They are phantom rows from the pre-v0.11 lifecycle, indistinguishable
from real data to every query that reads `status`. A one-line
`migrations`-adjacent note or a `legacy` marker would keep future analysis
honest. Worse, `studied_patterns` filters on neither `kind` nor `status`
(`db.py:264-284`), so a phantom row counts as engagement and permanently
suppresses the proactive learn offer for that pattern.

**S3.8 `stability` stops meaning what the docs say it means.** `MAX_INTERVAL_DAYS`
caps the *interval* but not stability (`scheduler.py:62`, `:88-98`), so after
about five good reviews `pattern_cards.stability` keeps growing (336+ days)
while every interval pins at 365 — and `docs/retention.md:5-7` defines stability
as "days to 90% recall", which is no longer true of the stored number.
`retention.md:25-26` also claims three good recalls reach "about 24 days"; the
actual sequence is 2 → 7 → 21 → 58 **[X]**, and `tests/test_scheduler.py` asserts
only `>= 7`, so nothing catches the drift. The FSRS-4.5 implementation itself
checks out: the 17 weights are the published defaults verbatim, every pinned
value in the tests re-derives independently, and the curve/interval algebra is
correct (including the FSRS-4.5-specific linear `D0`) — the model is honest, the
prose around it is not.

**S3.9 The strongest forgetting evidence is never recorded.** The recall grade is
asked only when the submit passed (`flow.py:1184-1187`), and quitting a warm-up
records nothing — so a *failed* warm-up (the clearest signal the schedule needs)
writes an attempt with `status='wrong_answer'` and no grade at all, and the
lapse branch is reachable only by re-solving successfully and then
self-reporting "forgot". Lapse rate is therefore systematically under-observed,
which biases every subsequent interval upward. [R]

**S3.10 `_grade` silently reinterprets an out-of-range grade.** `max(1, min(4,
int(grade)))` (`scheduler.py:68-69`) means a `0` or negative becomes grade 1 —
**a lapse** — and `5+` becomes grade 4 — **easy**, which multiplies the whole
grown stability by 2.61 **[X]**. The only interactive caller validates first
(`flow.py:946-957`), so this is a landmine for the next caller rather than a live
bug; it should raise.

**S3.11 Backfilled cards start their first review at R=1, so it is
information-free.** `record_grade` anchors elapsed time at
`last_review_at or created_at` (`scheduler.py:207-215`), and `backfill_cards`
inserts with `due_immediately=True` so both are the *backfill* time
(`scheduler.py:433-445`) — t ≈ 0 ⇒ R = 1 ⇒ the retrievability term
`(e^((1-R)·w10) - 1)` is exactly 0, and grading "good" moves stability
2.4 → 2.4 **[X]**. The true anchor (the latest correct `attempts.submitted_at`
for the pattern) is sitting in the DB. `backfill_cards` also ignores its
`grade=` argument, backfills **every** user while setup registers one, and
returns the number of (user, pattern) *pairs* rather than cards created — so
`setup.py` reports "backfilled N card(s)" on a second run that wrote nothing.

### S4 — ergonomics and product gaps

**S4.1 Post-solve mode drops `check` and `open`; the words are sent to the
model.** `_post_solve_loop` (`flow.py:896-917`) accepts `polish`, `done`/`quit`,
and treats *everything else* as a discussion question. Reproduced **[X]**: typing
`check` and then `open` in the post-solve loop produced two AI answers and never
ran the visible tests or opened the editor. Polishing is exactly when a student
wants to re-run the visible tests and re-read the code in the editor — and the
dispatcher silently answers a question they did not ask. (User report #2.)

**S4.2 `polish` means the wrong thing.** It is a re-grade alias
(`flow.py:781-871`): judge → re-collect complexity claims → re-measure → update
the row. The user's reading is better — *"take me back to solving mode, with the
discussion agent answering questions instead of the pre-submission tutor"* —
because polishing is an editing activity, and the current command makes it a
grading activity with an implicit code path. Fix in v0.13 §B: one loop, two
phases, one `submit` verb.

**S4.3 The AI reads dojo's chrome as if the student wrote it.** `_submit` passes
`code_path.read_text()` (`flow.py:700`) to `build_review_prompt`, which emits the
statement twice — once as `PROBLEM STATEMENT` and once inside the submitted code
as the module docstring — plus the venv shebang (`prompts.py:223-231`). Observed
verbatim in the live log: **15 of 18 reviewer responses** mention the shebang or
the docstring **[X]**, e.g. *"shebang — a module that is imported, not executed,
does not need one"* and *"module docstring is just the problem statement pasted
in, which is fine but…"*. One review even cites *"shebang on line 1 is flagged
by ruff (EXE001)"* — a finding ruff structurally cannot emit, since
`static.analyze` ignores EXE001 and returns `ruff: []` on the real template
**[X]**. So the reviewer is spending part of every review on dojo's own chrome,
and hallucinating lint findings to justify it. (User reports #3 and #4.)

**S4.4 The workbench has no runnable entry point.** The file is a shebang, a
docstring, and a bare `def` (`flow.py:68-104`) — so "Run"/"Debug" in the IDE
launches a file that defines a function and does nothing. The generated
`launch.json`/`debug.json` already point at `${file}`/`$ZED_FILE`
(`editor.py:155-189`), so the wiring is one `if __name__ == "__main__"` (or one
runner file + profile) away from working. (User feature idea #1; plan in v0.13
§C.)

**S4.5 One provider, hardcoded.** `DeepSeekBackend` pins
`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL` and `deepseek_api_key()`
(`tutor/backend.py:18-19`, `config.py:60-69`); `get_backend()` has two branches
(`mock`, `deepseek`); `chat_json` hardcodes `response_format={"type":
"json_object"}` and `temperature=0.0`; `chat` caps output at 2048 tokens
(`backend.py:72-145`). `openai` is already a dependency, so OpenAI is a base-URL
change, while Anthropic needs the `anthropic` SDK (it does not accept
`response_format`, and its system prompt is a top-level field). (User feature
idea #2; plan in v0.13 §D.)

**S4.6 `dojo progress`'s own footer has drifted.** "Stability = FSRS-lite
memory strength in days; the scheduler picks new problems follow the roadmap
order" (`cli.py:1205-1208`) — the model has been full FSRS-4.5 since v0.11
(AGENTS.md), the sentence has a grammar bug, and "FSRS-lite" contradicts
`docs/retention.md`.

**S4.7 `auto_update()` runs on every entry** (`cli.py:1466-1469`): an unannounced
`git fetch`/`merge --ff-only` plus a possible `uv sync` before the session
starts. In a two-person private repo this is fine and even nice; it is also a
network call on a code path whose docs promise "nothing here should ever need a
network call" (`config.py:1-6`), it can move the code under a running session,
and it is silently skipped whenever the working tree is dirty — which is exactly
the state a developer's checkout is in.

**S4.8 The prompt fallback is silent by design.** 29 `prompt_fallback` events
sit in the log, all `TypeError: object of type 'NoneType' has no len()`, all on
2026-09-11 — i.e. the v0.10.10 `default=None` bug, caught by the log and since
fixed **[X]**. The remarkable part is the *design*: when prompt_toolkit fails,
the user gets a dumber prompt with no visible warning, and only the debug log
knows. Now that it is logged, consider one dim line ("interactive prompt
degraded — see data/logs/dojo.log") so a user can tell the difference between
"dojo has no history" and "dojo fell back".

### S5 — content, identity, repo hygiene

**S5.1 The bank contains 18 duplicate problems.** `problems/` has both
`two_sum.py` and `two-sum.py`, `valid_parentheses.py` and
`valid-parentheses.py`, and 16 more pairs, because slug identity is the *file
stem* with no normalization (`bank.py:98`) and the hand-written snake_case files
and the fetched kebab-case files are different rows. Measured against the live
DB **[X]**: 182 rows for 179 files, 18 pairs differing only in `-` vs. `_`, and
in every pair the snake_case row is curated while the kebab row is permanently
dead (no registry decorator anywhere uses a kebab slug). `dojo list` filters
nothing, so the user is shown each of those 18 problems twice — once with
"Curated: —". The blast radius is otherwise contained: `_bank_lc` and
`_problem_by_lc` require `function_name IS NOT NULL`, so dead rows cannot be
served.

**S5.2 Three orphan rows survive renames.** `ensure_seeded` never deletes
(`bank.py:185-190`), and 179 files parse against 182 rows **[X]** — the three
extras are rows whose seed file was renamed or removed. They render in
`dojo list` and are eligible for the "dojo's own problems" fallback. A
soft-delete pass (mark rows whose source file vanished, hide them from list and
scheduler) would keep the additive-migration promise *and* stop serving ghosts.

**S5.3 The statement parser is strict in ways the corpus does not require.**
`bank.parse_problem_file` demands the file start with a docstring whose first
line matches `Title [Difficulty]` (`bank.py:78-89`) and silently returns None
otherwise — the importer prints a skip line but always exits successfully, so a
malformed new seed file lands as "nothing happened". Also note
`_COMPLEXITY_RE` requires the literal phrase "O(x) time and O(y) space"
(`bank.py:22-25`); a statement phrased differently silently has no expected
complexity, and the three-way table loses its Expected column.

**S5.4 Checked-in build artifacts.** `.pytest_cache/`, `.ruff_cache/`,
`.uv-cache/`, `src/dojo.egg-info/`, `problems/**/__pycache__/*.pyc`, and a
pre-v0.10.1 in-repo `workbench/` directory (with six stale solutions in it) are
in the working tree. `.gitignore` is doing its job for the first four; the
in-repo `workbench/` is a leftover whose files still look like real workbench
files.

**S5.5 `problems.difficulty` is a CHECK over LeetCode's three strings**
(`db.py:27`) — harmless today, and a wall for any curriculum whose items are not
"Easy/Medium/Hard" (JAX topics, Rust chapters). SQLite cannot relax a CHECK with
`ALTER TABLE`, so this becomes a table rebuild the first time a curriculum wants
its own vocabulary.

**S5.6 There is a reproducible flake, and it breaks the project's own hard
rule.** `tests/test_flow.py:1187` asserts `record["time"]["kind"] == "matches"`
on a *real* probe run whose ladder the test has shrunk to four sizes with one
repeat (`test_flow.py:275-290`) while the verdict is still derived from measured
millisecond ratios: 15 idle runs → 0 failures, 18 runs at 6-way concurrency → 6
failures (33%), error `assert 'unresolved' == 'matches'` **[X]**. AGENTS.md hard
rule 5 forbids exactly this ("a timing-based class assertion is a test of the
machine and will flake"), and `tests/test_probe.py:11-12` states the rule
verbatim while `tests/test_probe.py:242-254` — six sizes, five repeats, real
subprocesses, and a docstring that justifies itself with measured machine numbers
("0.87–1.04 across repeated runs, against the 0.71–1.40 matching band") — does the
same thing. `docs/development.md:19` ("measurement tests target coarse outcomes
(class, slope range)") contradicts the rule in the other direction; "slope" is
v0.11 fit-era vocabulary that no longer exists. Fix by pinning the *verdict* on
synthetic ratio series (which `tests/test_growth.py` already does correctly) and
having the end-to-end test assert only that a verdict was produced.

**S5.7 Large parts of the product have no test at all — and some tests cannot
fail.** `run_warmups` and `run_check` are referenced by zero tests, so the whole
warm-up contract AGENTS.md spells out (fresh template, `kind='warmup'`, no
reflection, quit records nothing) is unchecked; `db.migrate`, `ladder_state`,
`defer`, `render.review_markdown`, `patterns.PREREQS`/`GROUP_SLUGS`/`TAG_PRIORITY`,
`config.ai_backend`/`deepseek_api_key`, `updater.auto_update`, `state.state_path`/
`retire_state` and the non-TTY prompt path are likewise unreferenced. The CLI
layer is still the biggest hole: 10 of 17 `_cmd_*` handlers are never invoked and
`main()` appears exactly once in 6,642 lines of tests — with help argv only
(`tests/test_cli.py:374`), which is also why nothing has caught that `main([...])`
would run a real `git fetch` and touch the real DB. `tests/test_reference.py`
(493 lines) tests curator internals while `_cmd_reference` is never called, and
its "references survive the real judge" test enumerates 11 hardcoded slugs of
which 8 have a reference — so 20 of the 28 registered references have never been
through the real subprocess judge. Several tests would pass with the feature
deleted: `test_probe.py:107-112`'s in-place guard never mutates its input, so
removing every `deepcopy` from the probe keeps it green; `test_probe.py:138-143`
duplicates the assertions of `test_the_ascent_stops_at_the_failure`, so deleting
the "do not burn the remaining repeats" `break` keeps it green;
`test_reference.py:137-152` concedes in its own comment that it "passes either
way". And `judge/compare.py` — the module AGENTS.md calls "one implementation,
two callers" — has **zero** direct tests, which is how the documented
`"compare": "rounded:n"` tag came to be used by zero registry cases and zero
tests (dead documentation), and how every edge case in S1.10/S2.22 below stayed
invisible.

**S5.8 Versioning and build hygiene.** Three notions of version disagree:
`pyproject.toml:3` says `0.1.0`, `version.MAJOR_VERSION` says `0.10`, and the
shipped stage is v0.12. Neither the v0.11 nor the v0.12 commit touched
`version.py`, so the debug-log-clearing guard its own docstring mandates
(`version.py:3-5`) has not fired for two stages. `.pytest_cache/` and
`.ruff_cache/` are not covered by the root `.gitignore` (only by the ignore
files pytest and ruff generate inside themselves). `src/dojo.egg-info/` is stale
and describes deleted code — `SOURCES.txt` lists `src/dojo/profiler/fit.py` and
`tests/test_fit.py`, `PKG-INFO` still advertises the absolute-fit profiler — and
stale bytecode for deleted test modules survives in `tests/__pycache__/`. Seven
`.gitkeep` files sit in non-empty pattern directories. No CI, no pre-commit, no
lint/type-check config, no coverage gate, no `[tool.pytest.ini_options]`.

**S5.9 Two test paths still read real user state, and the safety is convention,
not a guard.** `_cmd_check` and `_cmd_report` import `WORKBENCH_DIR` *inside the
function* (`cli.py:598`, `cli.py:1074`), so `dojo.cli.WORKBENCH_DIR` cannot be
monkeypatched at all — any test that drives them reads the real
`~/.local/share/dojo/workbench`, which holds live user files. Two other
import-time-binding traps: `bank.seed_problems` calls `load_overrides()` with no
argument (`bank.py:140`), so a test seeding a tmp corpus still takes metadata
from the real `data/problem_overrides.json`; and `bank`'s path defaults are
frozen at import (`bank.py:108`, `:121`, `:139`), so patching `config` has no
effect unless the call site passes `root=`/`path=`. After a full run the real
DB, conf, log and workbench were all byte/mtime-identical and `git status` was
clean **[X]** — but `conftest.py` defines no autouse guard, so that is discipline
rather than protection. Also environment-fragile: `test_setup.py:134-148` leaves
key detection on and never clears ambient `DEEPSEEK_API_KEY`, so on a machine
with an exported key it takes the other branch and fails (clean here — no key in
the environment — so latent, not live).

**S5.10 Documentation drift, verified claim by claim.** Eighteen claims were
checked against the code; six are flatly wrong and the rest stale in detail:

- **`dojo open` does not exist.** `README.md:103` and AGENTS.md both describe
  it; there is no `open` subparser, so argv normalization rewrites it to
  `["day", "open"]` and the user gets *"Unknown problem 'open'"*. `open` is an
  in-session command; the CLI form is `dojo day --open`.
- **`dojo init` does not exist either** — documented in
  `docs/architecture.md:26`, `docs/curation.md:5`, and `docs/retention.md:57`,
  although `roadmap/v0.5.md` records its removal seven stages ago.
- **`docs/architecture.md:74` describes the pre-v0.11 in-session `learn`
  behavior** ("parks the current attempt… status stays 'unsolved'") one page
  away from `:90` describing the current behavior correctly; `flow.py:1147-1151`
  records nothing.
- **`tests/test_probe.py:11-12` contradicts `tests/test_probe.py:242-254`** in
  the same file about whether a test may assert a class from wall-clock timing —
  and `AGENTS.md` rule 5 and `docs/development.md:19` contradict each other on
  the same question ("slope" is v0.11 vocabulary that no longer exists).
- **`roadmap/README.md:16`** says "126 of 150 still to fetch"; the real split is
  126 uncurated / 24 curated (the fetching is done, `next.md` already concedes
  the wording).
- **`docs/grading.md:122`** describes the review as plain text through
  `de_markdown`; there is no display caller for `de_markdown` any more — the
  review renders as Markdown (`flow.py:775-778`), and AGENTS.md has this right.
- Stale in detail: `docs/architecture.md:36` still calls the scheduler
  "FSRS-lite" (AGENTS.md explicitly forbids that wording), `:101` says "seven
  everyday commands" (it is eight — `roadmap`), AGENTS.md's command inventory
  omits `reference` and `update`, its "delivered stages (v0.1..v0.11)" omits
  v0.12, `README.md` documents `dojo show` as an everyday command while the
  other two docs call it a hidden power tool, and `README.md`'s `make test`
  invocation (`uv run pytest`) differs from what the Makefile actually runs
  (`uv run python -m pytest -q` — a form `docs/development.md` calls
  load-bearing).

---

## 3. The four reported issues and the two feature ideas — verification

| Report | Verdict | Evidence |
|---|---|---|
| 1. `dojo show <id>` only shows the final solution; polish loses the original | **Confirmed, by design in the schema** | single `code` column, overwritten on every submit (`flow.py:630-635`) and every polish (`flow.py:847-856`); `polished` counts revisions, nothing keeps them |
| 2. Post-solve mode loses `check`/`open`; `polish` should be a mode switch | **Confirmed, and worse than reported** | `_post_solve_loop` (`flow.py:896-917`) has no `check`/`open` branch; the words are sent to the discussion model as questions — reproduced **[X]**. `polish` is a re-grade (`flow.py:781-871`) |
| 3. The reviewer nags about the shebang | **Confirmed, 15/18 reviews; and it hallucinates lint evidence** | reviewer prompt carries the raw file (`flow.py:700`, `prompts.py:225`); log grep **[X]**; ruff returns `[]` on the real template while one review cites EXE001 **[X]** |
| 4. The reviewer nags about the statement-as-docstring | **Confirmed, same root cause** | statement appears twice in the prompt (`prompts.py:224-225`); log shows three verbatim complaints **[X]** |
| F1. Make the workbench file runnable from the IDE | **Feasible, two designs; §C of v0.13** | `launch.json`/`debug.json` already target the active file (`editor.py:155-189`); visible tests are already data (`data/problem_overrides.json`) |
| F2. Support OpenAI and Claude, not just DeepSeek | **Feasible; seam exists, provider quirks do not** | `AIBackend` protocol + `get_backend()` (`backend.py:54-58`, `:257-260`); hardcoded base URL/model/`response_format` (`:70`, `:119`) |

---

## 4. If I were building dojo from scratch

Ordered by how much pain each choice would have prevented. Every item is
retrofittable; the rank is about cost, not feasibility.

1. **One session loop with an explicit phase, not two loops.** `run_day`'s
   `while True` (`flow.py:1094-1221`) plus a separate `_post_solve_loop`
   (`flow.py:896-917`) is the direct cause of S4.1 and S4.2: the command table
   is duplicated and the second copy has no `check`/`open`. From scratch:
   `phase ∈ {solving, post_solve}` and `agent ∈ {tutor, discussion}` as explicit
   state, one dispatcher, one command table, with per-phase command availability
   and the answering agent chosen by state rather than by which loop you are in
   (the concrete design is v0.13 §B). Adding a command then cannot forget a mode.

2. **Attempts as an append-only revision stream.** `attempts` (head) +
   `attempt_revisions(attempt_id, n, code, status, judge_summary, claims,
   measurement, review, created_at)`. This makes S2.1 impossible, gives the
   reviewer an honest "what changed since the last version" input, and turns
   *revision count to convergence* into a first-class learning signal (the
   `polished` counter already gestures at it, but throws away the content).
   The cost of retrofitting now is one additive table and a write in two places.

3. **A `WorkbenchFile` abstraction from day one.** One module owning: render a
   template from an item, identify and strip dojo chrome (shebang, statement
   docstring, generated `__main__` block), expose the *student* view, and expose
   the runnable entry point. Every reader (judge, `static`, probe, tutor,
   reviewer, discussion, `dojo show`) consumes the views rather than reading a
   path. That single abstraction is the structural fix for S4.3/S4.4 and F1 —
   versus the prompt patch ("please ignore the shebang") which will be
   re-broken by the next model and which cannot fix the hallucinated-EXE001
   class of noise at all.

4. **A role-carrying backend protocol, and a provider registry.**
   `chat(role: Role, system, user)` instead of `chat(system, user)` plus
   MockBackend guessing the role from a substring of the system prompt. That
   convention currently *constrains production prompt wording* — `TEACHER_SYSTEM`
   may not contain "tutor" or "discussion" (AGENTS.md; the discussion branch has
   silently died once) — which is a test fixture dictating product copy
   (`tests/test_prompt_routing.py` is the workaround). With roles named,
   providers become data: `{name, base_url, model, key_env, json_mode, system_field}`
   with per-role model overrides (a cheap model for the leak audit, the strong
   one for the review).

5. **Identity by `(curriculum, source_key)`, not by file stem.** `slug` as
   primary key plus a nullable `lc_number` alongside it produced S5.1 and made
   the roadmap's ladder key a special case. From scratch: an item key that is
   meaningful inside its curriculum, plus a source key for intake
   reconciliation, plus a soft-delete for vanished sources (S5.2).

6. **A runner spec instead of `sys.executable`.** `{"cmd": [...], "env": {...},
   "timeout": n, "parse": "json"|"cargo-test"}` — ~20 lines that make the judge
   language-agnostic. It is also the single cheapest prerequisite for the Rust
   curriculum (see v0.14) and for a per-curriculum interpreter/venv.

7. **One exception boundary for every AI and subprocess call.** A decorator or
   context manager ("degrade, log, keep the loop alive") applied at the call
   sites, so that no transient failure can end a session (S1.5), and so the
   fail-closed/fail-open decision for each role is explicit at the boundary
   rather than implicit in a `dict.get` default (S1.1).

8. **Provenance on every AI-derived value.** `ai_provenance` (backend, model,
   prompt version, rubric version) on the row, and a prompt-version constant
   bumped whenever a prompt changes. Review-score *trends* (`db.review_trends`)
   are only meaningful if the instrument did not change mid-series (S3.1).

9. **A curriculum-shaped schema from the start, even with one curriculum.**
   Units and prerequisites as data (a TOML that `load_roadmap` already almost
   is), unit names namespaced per curriculum so `pattern_cards` cannot collide,
   and difficulty as free text with a per-curriculum vocabulary instead of a
   CHECK (S5.5). The cost of doing this with one curriculum in the repo is
   small; the cost of doing it with three is a migration plus a fortnight of
   decoupling (v0.14's coupling inventory is 28 rows long).

10. **Tests that drive the product, not the functions.** 11 of 15 `_cmd_*`
    functions are never invoked by the suite and no test calls `main()`
    (next.md #11). One `main(["day", slug])` smoke test with a tmp DB and
    `FakeConsole` would have caught the `dojo check` slug bug (S2.8) and every
    future argument-normalization mistake. Also: no assertion should ever depend
    on a mock's prompt-substring routing (that pattern is why item 3 above
    exists).

11. **One version source of truth.** `pyproject.toml` (`0.1.0`),
    `version.MAJOR_VERSION` (`0.10`), and the roadmap stage (`v0.12`) disagree
    (S3.3). Derive the debug-log generation and the package version from one
    place.

12. **Say what the tool is before the loop runs.** A two-line "what today looks
    like" preamble and a `--explain` for the grader would have saved the learner
    from having to read `docs/grading.md` to understand a red cell. (Minor, but
    this is a product whose whole value is trust in its feedback.)

---

## 5. What I would keep, unchanged

- **The never-solve rule and its architectural enforcement** — including the
  guard test and the documented teacher narrowing. Nothing about a rewrite
  changes this; it is the product.
- **The evidence-never-verdict measurement contract** — paired reference,
  three-valued comparison, "unresolved is not a red cell", failures-as-findings.
  Keep the refusal to fit an absolute curve; keep writing down why.
- **AI proposes / machine disposes** — oracles and references admitted only
  against the brute-force anchor, `dojo report` auditing the curation.
- **The attempt row as the learner model** and the "an attempt exists iff the
  student submitted" semantics (`quit` records nothing).
- **The injected-seam style** — HTTP transport, update runner, backend, console,
  clock-free tests. It is why this audit could be done at all, and it is what
  makes v0.13/v0.14 cheap.
- **The debug log.** Whatever else changes, raw AI traffic must stay recorded
  (with a version-gated clear).
- **Additive-only migrations + "user data is real".**
- **The workbench outside the repo, with generated IDE config.**
- **The terminal ergonomics** (placeholder hints, typo guard, double-check gate,
  `patch_stdout`).
- **The docs/roadmap/AGENTS.md culture** — including the post-mortems. If
  anything in this repo deserves to be published, it is the habit of recording
  the *failed* design alongside the shipped one.

---

## 6. Suggested order of work

| Order | Item | Why first | Effort |
|---|---|---|---|
| 1 | S1.1 leak audit fail-closed | the headline promise is currently fail-open | S |
| 2 | S1.2 fd-level judge isolation + `run_cases` never raises | one `os.write` loses a session today | S |
| 3 | S1.6 conditional rollback delete in `curator.apply` | `report --fix` can delete a row attempts point at | S |
| 4 | S1.7 one transaction + guard for the card grade | a crash double-counts reps/lapses silently | S |
| 5 | S1.3/S1.4/S2.5/S2.6/S2.17 judge verdict hygiene | cheap, and they make every later signal trustworthy | S |
| 6 | S1.10 per-case arg copy + S1.8 output bounds + S1.9 process-group kill | live mis-grading, an OOM, and orphaned processes | S |
| 7 | S1.11 `reference_class` honesty | the probe's one constructed claim it cannot support | M |
| 8 | S5.6 pin the flake, then S5.7's missing-product tests | the suite must not lie about the machine | S |
| 9 | S1.5 exception boundary | turn "traceback" into "reviewer unavailable" everywhere | M |
| 10 | S2.1 + S4.1 + S4.2 (§A/§B of v0.13) | the session-continuity work the user asked for | M |
| 11 | S4.3 + S4.4 + F1 (§C of v0.13) | the workbench abstraction; unlocks the runnable file | M |
| 12 | F2 (§D of v0.13) | unlocks model choice, and the second curriculum's tooling | M |
| 13 | S5.1/S5.2/S2.13 bank identity + soft-delete + ladder tagging | stops the corpus drifting while v0.14 is designed | M |
| 14 | S2.15/S2.16 WAL, connection hygiene, schema version | concurrency is real (two users, one DB) and cheap to fix now | S |
| 15 | S5.10 doc drift + S5.8 hygiene sweep | an hour of truth-telling about what exists | S |
| 16 | v0.14 curricula (JAX first, Rust second) | the actual feature request | L |

Items 1–6 are a day's work and remove every S1 in this audit. Everything after
that is a product decision rather than a defect — with one exception worth
repeating: **S5.6/S5.7 are the reason the other items survived this long.** The
suite is green, fast, and offline, which is a real achievement; but it tests
functions rather than the product, so an entire class of defect (wrong CLI
argument, wrong status label, wrong table, a mutation that is never asserted)
sits outside its field of view.
