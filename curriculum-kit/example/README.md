# Demo curriculum — the format, by example

The smallest complete dojo curriculum: one topic, two items, and one of everything the
format can declare. It is the engine's test double and the starting point for a new
curriculum, so it stays deliberately tiny.

```
curriculum.toml                     # what this curriculum declares
items/has_pair.md                   # a statement (executable + measured item)
items/has_pair.py                   # the artifact the student opens
checks/has_pair.py                  # visible checks, shipped to the student
assessment/has_pair.py              # QUARANTINED: oracle, cases, reference, measure
items/explain_the_tradeoff.md       # a statement (judged item)
items/explain_the_tradeoff.answer.md  # the artifact: a written answer
assessment/explain_the_tradeoff.py  # QUARANTINED: the rubric
```

What it demonstrates, and what to copy:

- **Two evidence kinds.** `has_pair` is `measured`: it has an oracle, a generator, a
  reference and a measurement policy, so a solve earns both a correctness verdict and
  a paired comparison. `explain_the_tradeoff` is `judged`: no oracle exists or could,
  so it declares a rubric and the engine labels the result as weak evidence. Neither
  overstates itself.
- **The two namespaces.** `items/` and `checks/` are what the student and the tutor
  see; `assessment/` holds the answer in machine form and is quarantined from every
  agent.
- **An alias.** `sum_pair` is declared as the old id of `has_pair`, which is how a
  rename keeps a student's history addressable.
- **A real measurement axis.** The ladder grows the list length, and the baseline is
  the canonical `O(n)` reference — so a student who ships the double loop shows up as
  a trend, not as a slow-looking number.
- **A policy that could decline.** A curriculum whose subject does not scale returns
  `{"axis": None}` and the engine reports *not measurable here* rather than a number.
