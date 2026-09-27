"""QUARANTINED assessment for `has_pair`.

Nothing here may be shown to a student or to any AI agent that talks to one: the
oracle, the generator and the reference are the answer in machine form.
"""

from dojo.curriculum.registry import cases, measure, oracle, reference


@oracle("has_pair")
def _oracle(values: list[int], target: int) -> bool:
    """Obvious and slow: try every pair of distinct indices."""
    for i, a in enumerate(values):
        for j, b in enumerate(values):
            if i != j and a + b == target:
                return True
    return False


@reference("has_pair")
def _reference(values: list[int], target: int) -> bool:
    """The intended solution: one pass, remembering what has been seen."""
    seen: set[int] = set()
    for value in values:
        if target - value in seen:
            return True
        seen.add(value)
    return False


@cases("has_pair")
def _cases(n: int, rng):
    """Small cases, clamped into the statement's constraints (n arrives 0..12)."""
    n = max(0, min(n, 12))
    values = [rng.randint(-8, 8) for _ in range(n)]
    target = rng.randint(-8, 8)
    # Roughly half the cases should have a solution, so both branches are exercised.
    if values and rng.random() < 0.5:
        i, j = rng.sample(range(len(values)), 2) if n >= 2 else (0, 0)
        target = values[i] + values[j]
    return [values, target], _oracle(values, target)


@measure("has_pair")
def _measure(ctx):
    """Growing the list length should move the student and the reference apart by
    one class; the reference is the paired baseline."""
    return {"axis": "len(values)", "sizes": [64, 256, 1024, 4096], "baseline": "reference"}


# A literal naive baseline is only needed when the curriculum has no canonical
# reference to pair against; here the reference is the baseline, so `baseline` names
# it. See docs/curricula.md §5.
