# Prompt — author one item

Hand this to an AI agent for **one** item at a time, with the source material and the
curriculum's manifest in reach. One item, complete and gated, beats six sketched.

---

You are authoring a single item for a dojo curriculum. Read
`docs/curricula.md` (the format) and `curriculum-kit/example/` (a complete tiny
curriculum) in the dojo engine repository before you write anything.

## Inputs

- **Curriculum**: <path to the curriculum directory; its `curriculum.toml` fixes the
  topic ids, the display vocabulary and the language>
- **Topic**: <the topic id this item belongs to>
- **Item id**: <`[a-z][a-z0-9_]*`, stable forever>
- **Source material**: <the specific passage/page this item teaches>
- **Evidence kind**: <`executable` | `measured` | `judged` | `self-reported` — the
  plan's proposal; change it only with a stated reason>

## What to produce

Files, in the curriculum directory:

1. `items/<item>.md` — the statement the student reads. Title line, the task, worked
   examples where they help, the constraints, inputs and outputs, and — when a
   canonical complexity class expresses the point — a "You should aim for…" line.
   Write it in your own words; never paste a proprietary source.
2. `items/<item>.py` (or `.md` for a written answer) — the **artifact template**: the
   signature or prompt the student fills in, with a `TODO` body that runs and fails
   informatively. No hints, no partial solution, no imports you do not need.
3. `checks/<item>.py` — the **visible** checks: 3–6 cases from the statement's own
   examples plus the edges a student should think about. These are shipped to the
   student and appear in their workbench; they must be honest, self-contained, and
   consistent with the statement (including whether order matters).
4. `assessment/<item>.py` — **quarantined**. Register what the evidence kind requires:
   - `executable`: `@oracle` (a simple, obviously-correct brute force) **and**
     `@cases` (a generator `(n, rng) -> (args, expected)` or `(args, expected,
     extras)`). Tag any-order outputs with `compare: "sorted"`, floats with
     `compare: "approx:1e-4"` or `rounded:n`, and use a `@checker` only for genuine
     predicate problems (say in the statement that a checker validates the answer).
   - `measured`: also `@reference` (the intended-complexity solution the student is
     compared against) and `@measure` (the axis, the size ladder, and the baseline —
     "reference", or "naive" when the point of the item is a transformation that a
     naive implementation does not make).
   - `judged`: `@rubric` — the dimensions, what each score means, and what a pass
     requires. A rubric a reasonable person could apply consistently, not a vibe.
   - `self-reported`: nothing executable; say in the statement what the student is
     asserting.
5. A row for `curriculum.toml` — the complete `[[item]]` block.

## Gates to run before you report success

1. **It runs.** The template executes (and fails informatively), the checks import,
   and the assessment module registers under the item's own id.
2. **The oracle is right.** Solve the statement twice, independently, and compare on
   at least a hundred generated cases across the size ladder. If you cannot explain a
   disagreement, the statement is ambiguous — fix the statement.
3. **The reference agrees with the oracle** on every visible check and every generated
   case, under the same verdict tags. A reference that disagrees is refused, and it is
   worse than no reference: the measurement would then compare the student against a
   broken yardstick.
4. **The cases respect the statement.** Whatever the statement promises — sortedness,
   uniqueness, non-zero divisors, non-empty input, value ranges — the generator
   enforces. Never promise a property the cases ignore.
5. **The checks match the verdict vocabulary.** If the statement says "any order", the
   checks and the cases say so with a tag. Equality on a set of acceptable answers is
   the classic curation bug.
6. **It is measured, if you claimed it.** Run the measurement once locally and record
   what it reported. If the axis cannot separate the reference from the naive
   baseline, either find a better axis or declare the item `judged` — do not ship a
   measurement that cannot see the difference it is supposed to see.

## Rules

- **Never inflate the evidence kind.** The student's display shows the label; an
  `executable` item that silently has no oracle is the worst thing you can ship.
- **Never let assessment material leak.** Nothing in `items/` or `checks/` may quote,
  paraphrase so closely that it gives the answer away, or import from `assessment/`.
  Oracles and references are for machines, never for the tutor, the reviewer's
  reasoning, or the student.
- **Clamp sizes.** Generators receive `n` from 0 to 12 (or your curriculum's ladder)
  and must respect the statement's constraints at every `n`, including the smallest.
- **Prefer the smallest artifact that teaches the point.** If a second function or
  class is not the point of the item, do not require it.
- **Say what you could not do.** If a case is hard to generate, or the measurement is
  unstable, or you are unsure the item is `executable` rather than `judged`, report it
  in your summary rather than papering over it.

Report: the files written, the gate results (each one, with what you ran), and any
finding you could not resolve.
