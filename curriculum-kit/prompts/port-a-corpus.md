# Prompt — port an existing corpus into the format

Hand this to an AI agent when a body of practice already exists in some other shape —
a folder of problem files, a spreadsheet, a book's exercises, another trainer's export
— and it needs to become a dojo curriculum. The first corpus this is written for is
the NeetCode 150, currently living inside dojo's `main` branch.

---

You are porting an existing corpus into the dojo curriculum format. Read
`docs/curricula.md` (the format), `curriculum-kit/example/` (a complete tiny
curriculum), and `curriculum-kit/AGENTS.template.md` (the conventions of the
repository you are creating) first.

## Inputs

- **Corpus**: <paths — e.g. `problems/**/*.py` plus `data/problem_overrides.json` plus
  the oracle/generator code in `judge/registry.py`, on the branch named>
- **Target repository**: <path of the new curriculum repo>
- **Provenance**: <where the material came from, and its license>

## The mapping

Porting is a mapping exercise. Make every decision explicit, and write the mapping
down in the new repository's README so the next person can check it.

| corpus thing | becomes |
|---|---|
| a topic/group/pattern name | a `[[topic]]` with an id, a title, a summary, prerequisites |
| the corpus's ordering | `prereqs` edges (a graph — write down the *reason* for every edge you add that the corpus did not state) |
| one exercise | one `[[item]]`, with an id that is stable and readable |
| the exercise's text | `items/<item>.md` |
| the starter code / signature | `items/<item>.<ext>` (the artifact template) |
| the exercise's example cases | `checks/<item>.<ext>` (visible) |
| hidden/generated cases | `assessment/<item>.<ext>` — `@cases` |
| the correctness anchor | `@oracle` (quarantine) |
| the canonical solution | `@reference` (quarantine) |
| the "you should aim for O(…)" line | the statement's aim line, and the item's `measure` policy |
| the exercise's external id (a LeetCode number and the like) | `external_id` (unique inside the curriculum) |
| anything you cannot port | a line in the gaps section, not silence |

## Order of work

1. **Inventory the corpus.** How many items, how many already have an oracle and a
   generator, how many have a reference, how many are duplicates under different
   names, how many are not machine-checkable at all. Numbers, not impressions.
2. **Resolve identity first.** Two names for the same exercise must become one item.
   Match on the external id where it exists — never on the file name — and record
   every merge you make. A corpus that has drifted has usually drifted here, and the
   history attached to the losing name has to be preserved under the winner.
3. **Build the topic graph** from the corpus's grouping and ordering, and state where
   you inferred an edge the corpus did not.
4. **Port the items that are ready** (oracle + generator present) in one pass, running
   the gates in `prompts/author-an-item.md` per item. Report progress as
   `n of m ported`.
5. **List the items that are not ready** — no oracle, no generator, no reference —
   with what each one needs. Do not fabricate the missing pieces: an unported item is
   honest, an item with an invented oracle is a lie that grades students wrongly.
6. **Port the checks and the verdict tags.** Any-order outputs, floats, predicate
   answers and stateful class APIs each have a tag; a corpus that graded them by
   equality needs those tags added, and each addition is a finding worth reporting.
7. **Write the repository README**: what the curriculum covers, what it measures,
   what it judges, what is missing, and how the port was done (with the mapping
   table).

## Rules

- **The corpus is the source of truth for content; the format is the source of truth
  for shape.** Do not "improve" statements while porting — port, then report what you
  think is wrong. Silent edits make the port unauditable.
- **Never delete a name that has history.** Rename through `[aliases]`, and say in the
  README which names moved where.
- **Report the unportable.** Items whose material is proprietary, items whose grading
  relied on a human, items that no longer exist in the source — each is a line in the
  gaps section.
- **Keep the port reproducible.** Record the source commit or hash, the date, and the
  tool (or agent) that did it. A port nobody can re-run is a port nobody can fix.
- **Stop and ask** if the corpus's identity is ambiguous in a way that would change
  which items exist — merging the wrong two items destroys a student's history.

Report at the end: items ported, items deferred with reasons, identity merges made,
verdict tags added, and the coverage number (`ported / total`).
