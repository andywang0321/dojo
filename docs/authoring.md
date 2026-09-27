# Authoring — items, topics, and whole curricula

There are three ways a curriculum comes into being. They share one pipeline: a
proposal, a gate, an install — and the gate is what makes the difference between
content you can trust and content that merely runs.

| path | who authors | when it fits |
|---|---|---|
| **by hand** | you | the reference path, and the only one that needs no key |
| **with the curator** | an AI agent, gated by the engine | items for a subject you can describe precisely (a statement, checks, a reference) |
| **bootstrap** | an AI agent, from a source you trust | the case that motivated dojo: you want to learn something you are not expert in |

The last one is dojo's fourth claim. The first two are how it works today.

## 1. By hand

```bash
dojo curriculum new my-subject      # scaffold: manifest + one item + a check + an assessment stub
cd my-subject
$EDITOR curriculum.toml items/ checks/ assessment/
dojo curriculum validate .          # every problem, not the first
dojo enroll .                       # a working copy: symlinked, iterated live
```

What an item needs is in [curricula.md](curricula.md) §3. Two rules worth repeating
because they are the ones people get wrong: an item that declares `executable`
evidence must register an oracle *and* a generator (visible checks alone are not a
verdict), and an item you cannot check must say `judged` or `self-reported` rather
than quietly claiming more than it has.

## 2. With the curator

The curator is a **separate agent** from the tutor: it never sees student code, and
its output — oracles, generators, checkers, references — is judge infrastructure that
must never enter any agent's context. It turns a statement into an artifact set:

1. **Propose twice.** Two independent curator runs produce slug/title/topic,
   statement, function signature, visible checks, oracle, generator, optional checker,
   optional measurement input, optional reference.
2. **Differential check.** Both proposals are executed in isolated namespaces and
   their oracles are cross-checked on generated cases under strict equality. Any
   disagreement rejects the proposal — *the oracle is the trust root*, and one oracle
   alone is one opinion.
3. **Reference gate.** A canonical reference is optional but never admitted on trust:
   it must agree with the oracle on every visible check and generated case, judged by
   the judge's own verdict modes. A wrong baseline is worse than none, because the
   measurement would then derive confident verdicts from a broken yardstick.
4. **Apply with rollback.** The item, its metadata and its assessment module are
   written, the verification gate runs, and any failure rolls every touched file and
   registration back.

Provenance lands in gitignored `data/curation/<id>.proposal.json`, including the
engine's own repairs — because **model shape variance is repaired, never fatal, and
always announced**. A reference that arrives without its decorator gets one added; an
import the exec namespace cannot satisfy (the classic: `from decorators import
oracle`, for a module that does not exist because the decorators are *injected*) is
stripped and reported; a class-form answer for an op-list item gets the driver the
judge harness already uses. Every repair is written into the source too — the file is
what the next import reads — and printed, because a model that keeps misreading the
same instruction is evidence about the prompt.

The same stance governs the curator's own messages: a transport failure is reported
in plain language ("I'm having trouble connecting to the AI backend — is the network
connection ok?"), and everything the curator raises is a `CuratorError` so its caller
can roll back and report rather than crash.

## 3. Bootstrap — the fourth claim

You want JAX fluency for your research. You are not a JAX expert. You are therefore
not the person to design a JAX curriculum — but the agent is fluent, and there is a
source you already trust (the library's own documentation).

```
dojo curriculum bootstrap jax --from https://docs.jax.dev/ --out ./dojo-curriculum-jax
```

The pipeline, gated at every step:

1. **Ingest.** Fetch and reduce the source to text (the engine already has an
   `HTMLParser`-based reducer from the LeetCode intake; a local directory, a PDF
   conversion, or a syllabus works the same way). Record exactly what was ingested,
   with hashes, in the curriculum's provenance.
2. **Propose an outline.** Topics, order, prerequisites, and a one-line justification
   per topic — reviewed by *you* before any item is authored, because the graph is
   the pedagogical claim and it is cheaper to fix a graph than forty items.
3. **Author items** per topic, through the curator pipeline above, against the
   curriculum's declared evidence kinds. A topic whose material cannot be checked gets
   `judged` items and says so; nothing is dressed up as verification.
4. **Gate.** Each item passes its own gate (oracle agreement, reference agreement,
   checks that respect the statement). Ungated items are not servable.
5. **Audit the whole.** A curriculum-level audit: coverage against the source (what
   did the outline skip?), prereq sanity, duplicate `external_id`s, and an
   independent agent reading the outline against the ingested text to hunt material
   that was invented rather than sourced.
6. **Hand it over.** The result is a candidate curriculum in a directory, with a
   provenance record (source, commit/hashes, model, prompt versions, per-item gate
   results, coverage map), which you review, edit, enroll, and version like any other.

**Honesty rules for generated curricula**, because this is where a plausible-sounding
lie is easiest to produce:

- Provenance is per item, not per curriculum: which source passage, which model,
  which gate result. An item that cites a source that does not contain it is a bug
  worth reporting.
- Coverage is reported as *missing* where the outline skipped material; a generated
  curriculum is never presented as complete.
- `judged` and `self-reported` items stay labelled in the student's display. The
  generator does not get to promote its own confidence.
- Regeneration is explicit: a curriculum version is a snapshot, and re-running the
  bootstrap produces a diff, not a silent replacement.

## 4. Personalization, after the fact

A generated curriculum is a starting point. The evidence loop is what makes it
*yours*:

- **Placement.** A curriculum can declare a placement probe per topic: a few items
  whose verified outcome lets the outline skip what you already know instead of
  marching you through it. Skipped topics are recorded as skipped, not completed.
- **Reordering on evidence.** Topics whose items keep failing, or whose cards keep
  lapsing, are offered earlier; the schedule is the signal, not a hunch.
- **Just-in-time items.** When you hit a concept you have never met, the natural move
  is `learn` (the teacher) and then practice. Bootstrapping can generate that item on
  demand, gated like any other — the fourth claim and the third claim meeting.
- **Tuning the plan.** The generated `curriculum.toml` is a text file: difficulty
  ladder, warm-up policy, measurement axis, budgets. Editing it *is* personalization,
  and `dojo curriculum update` shows what changed.

## 5. The lifecycle of an item

```
proposed ──gate──▶ servable ──retired──▶ historical
   │                   │                    │
   │                   │                    └─ history stays addressable (aliases)
   │                   └─ attempts + cards reference it by (curriculum, item)
   └─ rejected: reported with its reason, never installed
```

Renaming is declared (`[aliases]`), retiring is declared (`retired = true`), and a
manifest that drops something with history fails validation instead of orphaning it.
The engine has been bitten by exactly this before: an identity carried by a filename
let eighteen problems exist twice, and the roadmap's curated/missing flag was decided
by dictionary-iteration order as a result.

## 6. Reporting a problem with someone's curriculum

`dojo report <item>` audits an item's assessment; `dojo report --curriculum <id>`
audits the whole thing (see [grading.md](grading.md) §9). Both accept the student's
own words, both print the automated cross-check findings so "nothing found" and "the
check never ran" cannot be confused, and both can propose a fix through the pipeline
with rollback. If you are using somebody else's curriculum, that report is the review
you would otherwise leave — and it is machine-readable enough to send upstream.
