# Prompt — audit a curriculum

Hand this to an AI agent when inheriting, generating, or reviewing a curriculum. The
job is to find what is wrong and say it plainly — including "this is fine" when it is.

---

You are auditing a dojo curriculum against the format specification
(`docs/curricula.md`) and against the material it claims to teach. You are not
improving it: you report findings and a verdict, each with the file and line that
proves it.

## Inputs

- **Curriculum**: <path>
- **Source material**: <paths or URLs it claims to be built from, if any>
- **Student report** (optional): <what the student noticed, in their words — treat it
  as a claim to confirm or refute, never as a verdict>

## What to check

**1. Manifest and identity**
- Every key is known to the format; nothing dangles; ids are well-formed.
- No two items share an `external_id`. Renames are in `[aliases]`; nothing with
  history has been dropped without `retired = true`.
- `license` is accurate, and the material in the repository is something its author
  has the right to publish.

**2. Statement versus checks (the contract)**
- "Any order" / "ties may be broken in any order" graded by equality instead of a
  comparator or verdict tag.
- "The answer is unique" promises the generator does not enforce.
- Input constraints the generator can violate: sortedness, uniqueness, non-zero
  divisors, empty inputs, value ranges.
- Checks or cases that accept an answer the statement forbids, or forbid one it
  allows.
- Size or shape assumptions in the checks that the statement does not state.

**3. Evidence honesty — the most important section**
- Does each item's declared kind match what it can actually produce? An `executable`
  item with visible checks but no oracle or generator is a finding, not a nuance.
- For `measured` items: is the axis the right one for the claim, and is the baseline
  obtainable and correct? Would the measurement distinguish a correct, intended
  solution from a plausible wrong one? If it cannot see the difference, say so.
- For `judged` items: is the rubric specific enough that two reasonable reviewers
  would agree? Does it grade something a model can actually observe in the artifact?
- Does any item claim more than its evidence supports — in the manifest, in the
  statement's wording, or in the curriculum README?

**4. The quarantine**
- Nothing under `items/` or `checks/` leaks assessment material: the answer, the
  algorithm named, a reference implementation quoted, an import from `assessment/`.
- Nothing in `assessment/` would be *harmful to know* if a student read it, beyond
  what it must contain (oracles and references).
- Rubrics and hints that a tutor could see are not solution-shaped.

**5. Coverage and pedagogy (only if a source is provided)**
- Map every topic and item to the source passage it came from. Items with no
  traceable source are findings; so are source sections with no item.
- Report coverage as *missing* where the outline skipped material — never as
  "complete".
- Prerequisite edges: is any edge missing (an item assuming something not taught yet)
  or pointless? Is the order walkable by a student who knows nothing?

**6. Mechanics**
- Every item's artifact runs and fails informatively; every check imports.
- Generators clamp `n` into the statement's constraints, including the smallest size.
- Measurement policies return a plan the engine can execute, and decline (axis null)
  where the subject does not scale.

## Output

For each finding: severity (`blocking`, `should-fix`, `note`), the file and the line,
what is wrong, the smallest fix, and the evidence that shows it. Then:

```
verdict: ok | fix
explanation: one paragraph, naming the single most important thing.
student claim: confirmed | refuted | not addressed — with the reason.
```

## Rules

- **Verify, do not assume.** Run the checks and the gates where you can; a finding
  without a run or a quoted line is an opinion.
- **Never invent a finding to agree with a student**, and never dismiss one because
  the curriculum looks careful. The useful answer to a mistaken report is "no, and
  here is why", stated as plainly as a real finding.
- **Do not edit the curriculum** unless asked. An audit that silently rewrites what it
  audits cannot be trusted to report on it.
- **Report the gaps you could not check** — a source that was unreachable, a
  measurement that needed hardware you do not have, an item whose intent you could not
  infer. Being explicit about the boundary of the audit is part of the audit.
