# The curriculum kit

Everything a third party needs to build a **dojo-compatible curriculum**. The engine
itself does not create curricula and does not curate problems: it enrolls what you
built and runs it. This directory is the interface.

```
curriculum-kit/
  README.md            # this file: the shape of a curriculum repo, and how to test it
  AGENTS.md            # the AGENTS.md a curriculum repository should start from
  prompts/             # prompts for an AI agent building a curriculum
    plan-a-curriculum.md
    author-an-item.md
    audit-a-curriculum.md
    port-a-corpus.md
  example/             # a complete, tiny curriculum — the format, by example
```

The normative specification is [`../docs/curricula.md`](../docs/curricula.md) in the
engine repository. This kit does not restate it; it shows it, and it gives an agent
the working instructions that the spec is not.

## What the engine will and will not do

| | |
|---|---|
| **Will** | install and validate a curriculum from a path or a git URL; import its catalog; serve its items; run its checks and assessment code in a bounded subprocess; schedule warm-ups by its policy; display its vocabulary; audit what is installed and report findings |
| **Will not** | author a curriculum; curate an item; generate or fix content; repair a broken check; install dependencies without consent; add AI roles, commands or evidence kinds |

Enrolling **is** validation: `dojo enroll ./my-curriculum` refuses a manifest it cannot
load, and prints every problem rather than the first. There is no separate
`validate` command by design — an author iterates on a working copy:

```bash
dojo enroll ./my-curriculum     # symlinked, not copied: edit and re-enroll
$EDITOR items/…
dojo enroll ./my-curriculum     # re-validates and re-imports
```

An enrolled path is a *working copy*; a URL is installed under
`~/.local/share/dojo/curricula/<id>/` with a `.dojo-source.json` recording the URL
and commit. Re-enrolling a URL is how a curriculum is updated.

## The shape of a curriculum repository

```
dojo-curriculum-<id>/
  curriculum.toml           # topics, items, policies, display words
  items/<item>.md           # the statement
  items/<item>.py|.md       # the artifact the student opens (a .md artifact is fine:
                            #   a judged item may be a written answer)
  checks/<item>.py          # visible, student-runnable checks
  assessment/<item>.py      # QUARANTINED: oracle, cases, reference, rubric, measurement
  README.md                 # what this curriculum claims, and what it does not
  AGENTS.md                 # start from ../AGENTS.md in this kit
  tests/                    # your own tests: the gates you run before publishing
  LICENSE                   # or `license = "private"` in the manifest: never publish
```

Two rules carry the whole design, and both are enforced:

1. **`assessment/` is quarantined.** It holds everything a student must not see —
   oracles, references, hidden cases, rubrics — and the engine never lets it near an
   AI agent. Put nothing there that you would not be willing to have graded against.
2. **The evidence kind is a promise.** `executable` items need an oracle *and* a
   generator (visible checks alone are not a verdict). Items you cannot check say
   `judged` or `self-reported` — and dojo will display that, so a student who is
   trusting your curriculum knows exactly what they are trusting.

## The gates, and when to run them

The engine runs these on load; you should run them before you publish, because a
curriculum that fails them is not servable.

| gate | what it establishes | how |
|---|---|---|
| **manifest** | the format is satisfied and nothing dangles | `dojo enroll .` |
| **oracle agreement** | your reference agrees with your oracle on every visible check and generated case | your own `tests/` (see below) |
| **case fidelity** | every generated case respects the statement's constraints (sortedness, uniqueness, ranges) | the audit prompt |
| **contract** | the statement and the checks agree — no "any order" graded by equality, no "unique answer" promise the generator breaks | `prompts/audit-a-curriculum.md`, and `dojo report` from the student side |
| **identity** | no two items share an `external_id`; renames are declared in `[aliases]` | `dojo enroll .` |

Write your own tests for the first two: a curriculum repository is a software
project, and its tests are offline and deterministic like the engine's. A useful
minimum is a test that loads every item's assessment module, generates cases at
several sizes, and asserts the oracle and the reference agree — the same gate the
engine applies, run where you can see it fail.

## Writing items

The fastest honest path is `prompts/author-an-item.md`: give the agent the source
material for one item and the format, and make it produce the statement, the
artifact, the visible checks, the assessment module and the measurement policy, with
the gates run as it goes. `prompts/plan-a-curriculum.md` is the step before that (a
topic graph from a source you trust), `prompts/port-a-corpus.md` is for an existing
body of problems, and `prompts/audit-a-curriculum.md` is what you run when you
inherit or generate one.

The four prompts are written to be handed to an agent verbatim, with the paths
filled in. They assume the agent can read the spec; they spell out the parts that are
easy to get subtly wrong — evidence kinds, the quarantine, gaps rather than
invention, and progress being reported as a percentage of a plan rather than as
prose.

## Public curricula, private sources

A curriculum is meant to be shareable — that is the point of a format — so the
manifest declares its `license` and its `source`. Two hard limits:

- `license = "private"` means **never publish this**, and the engine treats such a
  curriculum as local-only.
- Material you do not have the right to redistribute (a paid course's problem set, a
  book's exercises) belongs in a private repository, whatever the format allows.

Statements written by the curriculum's author are the norm and the safest option;
where a statement paraphrases a public source, cite it in the item's `source` field
and in the repository's README.
