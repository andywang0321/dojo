"""Every system prompt must reach its own canned branch.

`MockBackend` keys its branches on substrings of the system prompt. That
convention has silently broken twice: the discussion branch died and long tests
passed against the wrong fallback, and adding the reference branch shadowed the
curator branch because both prompts happened to contain the same phrase. Both
times the *tests* were the thing that failed to notice.

This file is the guard. Each prompt is routed through a backend whose branches
are distinct sentinels; a prompt that lands on the wrong branch — or on none —
fails here rather than in a session.
"""

from dojo.curator.prompts import AUDIT_SYSTEM, CURATOR_SYSTEM, REFERENCE_SYSTEM
from dojo.tutor.backend import MockBackend
from dojo.tutor.prompts import (
    DISCUSSION_SYSTEM,
    LEAK_CHECK_SYSTEM,
    REVIEWER_SYSTEM,
    TEACHER_SYSTEM,
    TUTOR_SYSTEM,
)

SENTINEL = {"curator": {"branch": "curator"}}


def _backend():
    return MockBackend(
        curator={"branch": "curator"},
        referencer={"branch": "reference"},
        auditor={"branch": "audit"},
        review={"branch": "review"},
        tutor={"branch": "tutor"},
        leak_ratings=[1],
        teacher="teacher-sentinel",
        discussion="discussion-sentinel",
    )


def test_each_json_prompt_reaches_its_own_branch():
    backend = _backend()
    assert backend.chat_json(CURATOR_SYSTEM, "x") == {"branch": "curator"}
    assert backend.chat_json(REFERENCE_SYSTEM, "x") == {"branch": "reference"}
    assert backend.chat_json(AUDIT_SYSTEM, "x") == {"branch": "audit"}
    assert backend.chat_json(REVIEWER_SYSTEM, "x") == {"branch": "review"}
    assert backend.chat_json(TUTOR_SYSTEM, "x") == {"branch": "tutor"}
    assert backend.chat_json(LEAK_CHECK_SYSTEM, "x") == {"rating": 1, "rewritten": ""}


def test_each_chat_prompt_reaches_its_own_branch():
    backend = _backend()
    assert backend.chat(TEACHER_SYSTEM, "x") == "teacher-sentinel"
    assert backend.chat(DISCUSSION_SYSTEM, "x") == "discussion-sentinel"


def test_the_reference_branch_does_not_shadow_the_curator_branch():
    """Regression: the reference prompt originally shared a phrase with the
    curator prompt, so `dojo curate` silently started receiving reference
    payloads."""
    backend = _backend()
    assert "canonical reference" in REFERENCE_SYSTEM.lower()
    assert "canonical reference" not in CURATOR_SYSTEM.lower()
    assert backend.chat_json(CURATOR_SYSTEM, "x")["branch"] == "curator"
    assert backend.chat_json(REFERENCE_SYSTEM, "x")["branch"] == "reference"


def test_branch_order_resolves_each_prompt_to_its_own_branch():
    """The precise property the substring convention must satisfy.

    Prompts *do* share words — CURATOR_SYSTEM mentions that it is not a tutor,
    so "tutor" appears in it too. A collision is harmless as long as the
    intended branch is tested first, so what matters is which key wins, in the
    order `chat_json` tests them.
    """
    # Branches as `chat_json` tests them: (branch, keys that select it). The
    # reviewer branch deliberately tests two words, so grouping by branch (not
    # by word) is what mirrors the code.
    json_branches = (
        ("audit", ("curation auditor",)),
        ("leak", ("auditor",)),
        ("review", ("rubric", "review")),
        ("reference", ("canonical reference",)),
        ("curator", ("curator",)),
        ("tutor", ("tutor",)),
    )
    prompts = {
        "curator": CURATOR_SYSTEM,
        "reference": REFERENCE_SYSTEM,
        "audit": AUDIT_SYSTEM,
        "review": REVIEWER_SYSTEM,
        "leak": LEAK_CHECK_SYSTEM,
        "tutor": TUTOR_SYSTEM,
    }
    for name, prompt in prompts.items():
        low = prompt.lower()
        winner = next(
            (branch for branch, keys in json_branches if any(k in low for k in keys)),
            None,
        )
        assert winner == name, f"{name} would be served by '{winner}', not '{name}'"

    chat_order = ("discussion", "post-solve", "teacher")
    chat_expected = {"discussion": "post-solve", "teacher": "teacher"}
    for name, want in chat_expected.items():
        prompt = DISCUSSION_SYSTEM if name == "discussion" else TEACHER_SYSTEM
        low = prompt.lower()
        winner = next((key for key in chat_order if key in low), None)
        assert winner == want, f"{name} would be served by '{winner}', not '{want}'"
