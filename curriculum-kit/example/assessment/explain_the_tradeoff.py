"""QUARANTINED assessment for `explain_the_tradeoff`: the rubric, and nothing else.

A judged item has no oracle and no cases — that is the honest shape for a question
whose answer is an argument. The engine will say `judged` wherever it reports this
item's evidence, and the schedule treats the result as weak evidence.
"""

from dojo.curriculum.registry import rubric


@rubric("explain_the_tradeoff")
def _rubric() -> dict:
    return {
        "dimensions": [
            {
                "name": "specificity",
                "prompt": (
                    "Does the answer name concrete conditions (input sizes, call "
                    "frequency, allocation cost, data layout) rather than restating "
                    "the asymptotic trade-off?"
                ),
                "anchors": {1: "generic", 3: "one concrete condition", 5: "two or more, with magnitudes"},
            },
            {
                "name": "correctness of reasoning",
                "prompt": (
                    "Are the stated conditions actually true of the two "
                    "implementations? Does the answer account for the set's memory "
                    "cost as well as its time?"
                ),
                "anchors": {1: "incorrect", 3: "broadly right", 5: "precise, including the space cost"},
            },
            {
                "name": "falsifiability",
                "prompt": (
                    "Could someone disagree with this answer on the evidence it "
                    "gives? An answer nobody can argue with has not said anything."
                ),
                "anchors": {1: "unfalsifiable", 3: "arguable", 5: "states what would change their mind"},
            },
        ],
        "pass": "score >= 3 on every dimension",
        "note": (
            "Judge the argument the student made, not the argument you would have "
            "made. Do not supply a better answer, and do not add a solution to the "
            "first exercise."
        ),
    }
