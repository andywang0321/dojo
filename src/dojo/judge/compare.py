"""Per-case verdict semantics, shared by the judge harness and the curator gate.

These functions used to live inside the judge harness string, which meant only
the harness could apply them. The v0.12 reference gate has to judge a canonical
solution by exactly the same rules the judge will use on the student's, so they
moved here — one implementation, two callers, and no chance of the two drifting
apart.

The harness runs as a subprocess with the venv's interpreter and already imports
dojo modules, so importing this is no different from importing the registry.
"""

from __future__ import annotations

import json


def canonical(value):
    """Deep-sort lists (and dicts by key) for order-insensitive compare."""
    if isinstance(value, list):
        key = lambda v: json.dumps(v, sort_keys=True, default=str)
        return sorted((canonical(v) for v in value), key=key)
    if isinstance(value, dict):
        key = lambda kv: json.dumps(kv[0], sort_keys=True, default=str)
        return [(k, canonical(v)) for k, v in sorted(value.items(), key=key)]
    return value


def rounded(value, ndigits):
    if isinstance(value, float):
        return round(value, ndigits)
    if isinstance(value, list):
        return [rounded(v, ndigits) for v in value]
    if isinstance(value, dict):
        return {k: rounded(v, ndigits) for k, v in value.items()}
    return value


def approx_equal(a, b, tol):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol if isinstance(a, float) or isinstance(b, float) else a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(approx_equal(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(approx_equal(a[k], b[k], tol) for k in a)
    return a == b


def check_equal(got, expected, mode: str) -> bool:
    """Apply one case's verdict mode. Default is strict JSON equality."""
    if mode.startswith("approx"):
        tol = float(mode.split(":", 1)[1]) if ":" in mode else 1e-9
        return approx_equal(got, expected, tol)
    if mode.startswith("rounded"):
        ndigits = int(mode.split(":", 1)[1]) if ":" in mode else 4
        got, expected = rounded(got, ndigits), rounded(expected, ndigits)
    elif mode == "sorted":
        got, expected = canonical(got), canonical(expected)
    return json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True)
