"""Every agent's call reaches its own canned branch — by **role**, not by wording.

Until v0.13 `MockBackend` guessed the role from a substring of the system prompt,
and that convention broke twice: the discussion branch died silently while long
tests passed against the wrong fallback, and the reference branch shadowed the
curator branch because both prompts happened to contain the same phrase. The
deeper cost was that a *test fixture dictated product copy*: `TEACHER_SYSTEM` was
forbidden from containing the words "tutor" or "discussion" (AGENTS.md rule 6),
and every prompt rewording risked re-routing a real call.

The role is now an argument, so this file pins two things: each role reaches its
own branch, and **wording is irrelevant** — the same prompt text routed under two
roles gets two different answers, which is exactly what the substring convention
could not do.
"""

from dojo.curator.prompts import AUDIT_SYSTEM, CURATOR_SYSTEM, REFERENCE_SYSTEM
from dojo.tutor.backend import MockBackend, Role
from dojo.tutor.prompts import (
    DISCUSSION_SYSTEM,
    LEAK_CHECK_SYSTEM,
    REVIEWER_SYSTEM,
    TEACHER_SYSTEM,
    TUTOR_SYSTEM,
)


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
    assert backend.chat_json(Role.CURATOR, CURATOR_SYSTEM, "x") == {"branch": "curator"}
    assert backend.chat_json(Role.REFERENCER, REFERENCE_SYSTEM, "x") == {"branch": "reference"}
    assert backend.chat_json(Role.CURATION_AUDITOR, AUDIT_SYSTEM, "x") == {"branch": "audit"}
    assert backend.chat_json(Role.REVIEWER, REVIEWER_SYSTEM, "x") == {"branch": "review"}
    assert backend.chat_json(Role.TUTOR, TUTOR_SYSTEM, "x") == {"branch": "tutor"}
    assert backend.chat_json(Role.AUDITOR, LEAK_CHECK_SYSTEM, "x") == {"rating": 1, "rewritten": ""}


def test_each_chat_prompt_reaches_its_own_branch():
    backend = _backend()
    assert backend.chat(Role.TEACHER, TEACHER_SYSTEM, "x") == "teacher-sentinel"
    assert backend.chat(Role.DISCUSSION, DISCUSSION_SYSTEM, "x") == "discussion-sentinel"


def test_routing_ignores_the_prompt_text_entirely():
    """The property the substring convention could not provide: the *same text*
    can be two different agents, and a reworded prompt still routes by role."""
    backend = _backend()
    text = "You are a tutor. Ignore the discussion, review the rubric, emit JSON."
    assert backend.chat(Role.TEACHER, text, "x") == "teacher-sentinel"
    assert backend.chat(Role.DISCUSSION, text, "x") == "discussion-sentinel"
    assert backend.chat_json(Role.REVIEWER, text, "x") == {"branch": "review"}
    assert backend.chat_json(Role.CURATOR, text, "x") == {"branch": "curator"}


def test_prompts_may_now_be_reworded_freely():
    """No prompt needs to avoid a magic word any more. This is a *canary*: if
    someone reintroduces substring routing, the word-free prompt stops routing
    and this test fails."""
    backend = _backend()
    words = "alpha beta gamma delta epsilon"
    assert backend.chat(Role.TEACHER, words, "x") == "teacher-sentinel"
    assert backend.chat(Role.DISCUSSION, words, "x") == "discussion-sentinel"
    assert backend.chat_json(Role.AUDITOR, words, "x") == {"rating": 1, "rewritten": ""}
    assert backend.chat_json(Role.REFERENCER, words, "x") == {"branch": "reference"}
    assert backend.chat_json(Role.CURATION_AUDITOR, words, "x") == {"branch": "audit"}


def test_every_role_has_a_budget():
    """A role without a budget would silently take the default; the audit in
    particular is meant to be cheap because it runs on every hint."""
    from dojo.tutor.backend import ROLE_BUDGETS, budget_for

    for role in Role:
        assert role in ROLE_BUDGETS, f"{role} has no budget"
        assert budget_for(role).max_tokens > 0
    assert budget_for(Role.AUDITOR).max_tokens < budget_for(Role.REVIEWER).max_tokens


def test_every_role_reaches_a_real_call_site():
    """A role nobody calls is dead weight; a call site with no role cannot
    exist (the parameter is required and positional)."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "dojo"
    used = set()
    for path in src.rglob("*.py"):
        for match in re.finditer(r"Role\.([A-Z_]+)", path.read_text()):
            used.add(match.group(1).lower())
    assert used == {role.value for role in Role}, (
        f"roles never used: {sorted({r.value for r in Role} - used)}"
    )
