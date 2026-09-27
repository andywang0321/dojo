# Prompt — plan a curriculum from a source

Hand this to an AI agent together with the source material. It produces a **plan to
review**, not items: fixing a topic graph is cheap, fixing forty items written
against the wrong graph is not.

---

You are planning a dojo curriculum. Read the format specification first —
`docs/curricula.md` in the dojo engine repository — and `curriculum-kit/example/`
for a complete (tiny) curriculum in that format.

## Inputs

- **Subject**: <what the student wants to learn, in their words>
- **Student**: <their background — what they already know, what they are weak at>
- **Source material**: <paths or URLs; a library's documentation, a syllabus, a book's
  table of contents, a course page>
- **Target**: <how much time, how deep, what "fluent enough" means>

## What to produce

A single markdown plan, in this shape:

1. **What the source actually covers.** A short inventory: the concepts it teaches,
   with a citation for each (file, section, URL fragment). If two sources disagree or
   one is thin, say so here.
2. **What it does not cover.** Explicit gaps — the topics a student of this subject
   would expect and this source does not teach. This section is mandatory and may not
   be empty; every body of material has edges, and a plan that claims total coverage
   is a plan that has not read closely.
3. **The topic graph.** Topics with ids (`[a-z][a-z0-9_]*`), titles, one-line
   summaries, and prerequisite edges. Rules:
   - every topic must earn its place by being independently *practisable* and
     independently *forgettable* (if it can never be its own warm-up, it is a
     section of another topic, not a topic);
   - prerequisites form a graph, not a chain; state the *reason* for each edge;
   - order the topics so a student can meet each concept before anything that assumes
     it, and mark the ones that are optional or advanced.
4. **Items per topic.** For each topic, propose 3–6 items with: an id, a one-line
   description of what the student does, the **evidence kind** it can honestly
   produce (`executable`, `measured`, `judged`, `self-reported`), and — for anything
   `measured` — the axis you intend to measure along and the baseline you would
   compare against (a canonical implementation, or a deliberately naive one).
5. **The warm-up answer.** For each topic: what does recall mean here? Re-solving the
   same item from scratch, re-deriving it with fresh inputs, or justifying a choice in
   writing. Be concrete — "review the material" is not an answer.
6. **The risky claims.** Anything you would be uncomfortable defending: a topic you
   suspect the source teaches badly, an item whose evidence kind you are unsure of, a
   measurement whose baseline you cannot obtain. List them; do not bury them.
7. **A draft `curriculum.toml`** with the topics, the prerereq edges and the item ids
   — no statements, no checks, no assessment modules yet. This is the artifact the
   human edits before item authoring starts.

## Rules

- **Never invent content that is not in the source.** If a topic belongs in the
  subject but the source does not cover it, it goes in the gaps section. If you add it
  anyway (because the student asked you to), mark the item `source = "generated"` and
  say why.
- **Do not write statements, checks, or solution material in this step.** You are
  producing a plan; item authoring has its own prompt and its own gates.
- **Cite as you go.** Every claim about the source gets a pointer. A plan whose
  citations cannot be checked is a plan nobody can trust.
- **Prefer fewer, better topics.** A curriculum of twelve topics a student finishes is
  worth more than one of forty they abandon, and every topic carries warm-up cost
  forever.
- **Ask before assuming the student's level.** If the target is ambiguous, state the
  assumption you made in one line at the top and proceed.

Finish by asking the human to review the graph and the item list before you continue
to authoring.
