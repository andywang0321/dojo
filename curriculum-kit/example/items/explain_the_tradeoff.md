# When is the slow version the right one? [core]

The previous exercise has an `O(n)` solution and an obvious `O(n^2)` one. Write a
short argument — **three to five sentences** — for a case where you would ship the
slower version anyway, and one where you would not.

Your answer goes in `explain_the_tradeoff.answer.md`. There is no test that can grade
this: it is judged against the rubric in the curriculum, and the display will say so.

Aim to be specific. "It depends on the input" is true and useless; `n = 8 in a hot
loop, where the set costs an allocation per call` is a claim someone can argue with.
