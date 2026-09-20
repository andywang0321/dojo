"""Per-pattern review-score trends (dojo progress, v0.4).

Scores are weighted by recency (the oldest attempt of n gets weight 1, the
newest gets n) so late improvement counts more than early flailing.
"""

import pytest

from dojo.db import trends_from_rows

DIMS = (
    "correctness",
    "approach_quality",
    "style_idiom",
    "naming",
    "edge_cases",
    "complexity_claim_check",
    "complexity_reasoning",
)


def _review(scores: dict) -> dict:
    return {dim: {"score": scores.get(dim, 5), "comment": "ok"} for dim in DIMS}


def _rows(*pattern_reviews):
    """(pattern, review_dict) pairs, oldest first — the query's order."""
    return [(pattern, review) for pattern, review in pattern_reviews]


def test_weighted_average_favors_recent_attempts():
    rows = _rows(
        ("stack", _review({"correctness": 2})),
        ("stack", _review({"correctness": 5})),
    )
    trends = trends_from_rows(rows)
    assert len(trends) == 1
    entry = trends[0]
    assert entry["pattern"] == "stack"
    assert entry["solves"] == 2
    # weights 1 (old) and 2 (new): (2*1 + 5*2) / 3
    assert entry["dims"]["correctness"] == pytest.approx(round(12 / 3, 2))
    # other six dims are 5s; overall = round((4 + 6*5) / 7, 2)
    assert entry["overall"] == pytest.approx(round(34 / 7, 2))


def test_groups_by_pattern_and_excludes_missing_reviews():
    rows = _rows(
        ("stack", _review({"correctness": 4})),
        ("heap", _review({"correctness": 3})),
        ("heap", None),  # attempts without a review are excluded
        ("stack", None),
    )
    trends = trends_from_rows(rows)
    by_pattern = {t["pattern"]: t for t in trends}
    assert set(by_pattern) == {"stack", "heap"}
    assert by_pattern["stack"]["solves"] == 1
    assert by_pattern["heap"]["solves"] == 1
    assert by_pattern["heap"]["dims"]["correctness"] == pytest.approx(3)


def test_malformed_reviews_are_skipped():
    rows = _rows(
        ("stack", _review({"correctness": 4})),
        ("stack", "not a dict"),
        ("stack", {"correctness": "no score key here"}),
    )
    trends = trends_from_rows(rows)
    assert trends[0]["solves"] == 1


def test_empty_rows():
    assert trends_from_rows([]) == []


def test_review_trends_query_runs(db):
    from dojo.db import dumps_json, get_or_create_user, now, review_trends

    db.execute(
        """
        INSERT INTO problems (slug, title, difficulty, pattern, statement, created_at)
        VALUES ('valid_parentheses', 'Valid Parentheses', 'Easy', 'stack', 's', ?)
        """,
        (now(),),
    )
    uid = get_or_create_user(db, "andy")
    pid = db.execute("SELECT id FROM problems WHERE slug='valid_parentheses'").fetchone()["id"]
    for score in (3, 5):
        db.execute(
            """
            INSERT INTO attempts (user_id, problem_id, kind, status, started_at, review)
            VALUES (?, ?, 'solve', 'correct', ?, ?)
            """,
            (uid, pid, now(), dumps_json(_review({"correctness": score}))),
        )
    db.commit()
    trends = review_trends(db, uid)
    assert len(trends) == 1
    assert trends[0]["pattern"] == "stack"
    assert trends[0]["solves"] == 2
    assert trends[0]["dims"]["correctness"] == pytest.approx(round((3 + 5 * 2) / 3, 2))


def test_warm_ups_are_not_solves(db):
    """Warm-ups store a full review too, so the recency-weighted trend mixed
    first solves with hint-free recall re-solves while calling the total
    "solves" (v0.13 audit, S2.14)."""
    from dojo.db import dumps_json, get_or_create_user, now, review_trends

    uid = get_or_create_user(db, "andy")
    db.execute(
        "INSERT INTO problems (slug, title, difficulty, pattern, statement, "
        "function_name, visible_tests, created_at) VALUES "
        "('p','P','Easy','stack','s','f','[]',?)",
        (now(),),
    )
    db.commit()
    pid = db.execute("SELECT id FROM problems").fetchone()["id"]
    review = {
        dim: {"score": 5, "comment": ""}
        for dim in (
            "correctness", "approach_quality", "style_idiom", "naming",
            "edge_cases", "complexity_claim_check", "complexity_reasoning",
        )
    }
    for kind in ("solve", "warmup"):
        db.execute(
            "INSERT INTO attempts (user_id, problem_id, kind, status, started_at, "
            "submitted_at, review) VALUES (?, ?, ?, 'correct', ?, ?, ?)",
            (uid, pid, kind, now(), now(), dumps_json(review)),
        )
    db.commit()

    trends = review_trends(db, uid)
    assert len(trends) == 1
    assert trends[0]["solves"] == 1  # the solve, not the recall re-solve
