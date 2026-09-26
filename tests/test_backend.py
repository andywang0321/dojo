"""The provider layer: request construction, per-role budgets, JSON handling.

No test here touches the network. Each backend takes an injectable client, so
these tests assert *what dojo would send* (the system prompt's address, the
model, the budget, `response_format` presence) and *how it reads what comes
back* (OpenAI-compatible content, Anthropic tool_use, Anthropic prose fallback).
That is the part dojo controls; the part it does not — whether a provider
honours the request — is what one manual pass per provider is for.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojo.config import PROVIDERS, detect_provider_key, role_model
from dojo.tutor.backend import (
    JSON_MAX_TOKENS,
    JSON_TOOL,
    AnthropicBackend,
    MockBackend,
    OpenAICompatBackend,
    Role,
    budget_for,
    build_backend,
    parse_json_content,
)


# ------------------------------------------------------------- fake clients


class FakeCompletions:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAIClient:
    def __init__(self, content: str = "{}"):
        self.completions = FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeMessages:
    def __init__(self, blocks: list):
        self.blocks = blocks
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self.blocks)


class FakeAnthropicClient:
    def __init__(self, blocks: list):
        self.messages = FakeMessages(blocks)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_block(payload: dict):
    return SimpleNamespace(type="tool_use", name="emit_json", input=payload)


# --------------------------------------------------------------- provider table


def test_the_provider_table_describes_three_providers():
    assert set(PROVIDERS) == {"deepseek", "openai", "anthropic"}
    assert PROVIDERS["deepseek"].wire == "openai"
    assert PROVIDERS["deepseek"].base_url == "https://api.deepseek.com"
    assert PROVIDERS["openai"].base_url is None  # the SDK default
    assert PROVIDERS["anthropic"].wire == "anthropic"
    # No `response_format` at Anthropic: JSON comes back through a tool call.
    assert PROVIDERS["anthropic"].json_mode == "tool"
    assert PROVIDERS["openai"].json_mode == "object"


def test_an_unknown_provider_fails_loudly():
    with pytest.raises(RuntimeError, match="unknown AI backend"):
        build_backend("gpt5-turbo-ultra")


def test_mock_is_still_reachable_by_name():
    assert isinstance(build_backend("mock"), MockBackend)


def test_a_missing_key_names_the_variable(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "DOJO_DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("dojo.config._read_dotenv", lambda key: None)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        OpenAICompatBackend(PROVIDERS["deepseek"])
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicBackend(PROVIDERS["anthropic"])


def test_detection_prefers_the_table_order(monkeypatch):
    monkeypatch.setattr(
        "dojo.config.resolve_key", lambda provider: "k" if str(provider) in ("openai",) else None
    )
    assert detect_provider_key() == ("openai", "k")


# ------------------------------------------------------- OpenAI-compatible wire


def test_openai_request_carries_the_system_prompt_as_a_message():
    client = FakeOpenAIClient('{"ok": true}')
    backend = OpenAICompatBackend(PROVIDERS["openai"], api_key="sk-test", client=client)
    backend.chat_json(Role.REVIEWER, "SYSTEM PROMPT", "USER PROMPT")
    call = client.completions.calls[0]
    assert call["messages"] == [
        {"role": "system", "content": "SYSTEM PROMPT"},
        {"role": "user", "content": "USER PROMPT"},
    ]
    assert call["response_format"] == {"type": "json_object"}
    assert call["model"] == PROVIDERS["openai"].model
    assert call["max_tokens"] == JSON_MAX_TOKENS  # the reviewer's budget


def test_the_audit_gets_a_small_budget_and_temperature_zero():
    """The leak audit runs on every hint, so it must not pay for a review-sized
    completion — and a rating should not be sampled."""
    client = FakeOpenAIClient('{"rating": 1}')
    backend = OpenAICompatBackend(PROVIDERS["deepseek"], api_key="sk-test", client=client)
    backend.chat_json(Role.AUDITOR, "audit", "response")
    call = client.completions.calls[0]
    assert call["max_tokens"] == budget_for(Role.AUDITOR).max_tokens
    assert call["temperature"] == 0.0
    assert call["max_tokens"] < budget_for(Role.REVIEWER).max_tokens


def test_a_plain_chat_sends_no_response_format():
    client = FakeOpenAIClient("just prose")
    backend = OpenAICompatBackend(PROVIDERS["deepseek"], api_key="sk-test", client=client)
    assert backend.chat(Role.TUTOR, "s", "u") == "just prose"
    assert "response_format" not in client.completions.calls[0]


def test_the_deepseek_host_comes_from_the_table():
    """DeepSeek and OpenAI share the wire format; only the base URL, model and
    key differ. Building the SDK client is the one place the URL is read."""
    seen: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions("{}"))

    import openai

    original = openai.OpenAI
    openai.OpenAI = FakeOpenAI
    try:
        OpenAICompatBackend(PROVIDERS["deepseek"], api_key="sk-test")
    finally:
        openai.OpenAI = original
    assert seen["base_url"] == "https://api.deepseek.com"
    assert seen["api_key"] == "sk-test"


# --------------------------------------------------------------- Anthropic wire


def test_anthropic_sends_the_system_prompt_top_level():
    client = FakeAnthropicClient([_tool_block({"rating": 2})])
    backend = AnthropicBackend(PROVIDERS["anthropic"], api_key="sk-test", client=client)
    backend.chat_json(Role.AUDITOR, "SYSTEM PROMPT", "USER PROMPT")
    call = client.messages.calls[0]
    assert call["system"] == "SYSTEM PROMPT"
    assert call["messages"] == [{"role": "user", "content": "USER PROMPT"}]
    assert "response_format" not in call  # Anthropic has no such parameter
    assert call["max_tokens"] > 0


def test_anthropic_json_comes_back_through_a_forced_tool_call():
    client = FakeAnthropicClient([_tool_block({"correctness": {"score": 5}})])
    backend = AnthropicBackend(PROVIDERS["anthropic"], api_key="sk-test", client=client)
    parsed = backend.chat_json(Role.REVIEWER, "s", "u")
    assert parsed == {"correctness": {"score": 5}}
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": JSON_TOOL["name"]}
    assert call["tools"][0]["name"] == JSON_TOOL["name"]


def test_anthropic_falls_back_to_parsing_prose():
    """A model that answers in text instead of calling the tool still works:
    the same tolerant extractor every other provider uses reads it."""
    client = FakeAnthropicClient([_text_block('Sure!\n```json\n{"rating": 1}\n```')])
    backend = AnthropicBackend(PROVIDERS["anthropic"], api_key="sk-test", client=client)
    assert backend.chat_json(Role.AUDITOR, "s", "u") == {"rating": 1}


def test_anthropic_plain_chat_joins_its_text_blocks():
    client = FakeAnthropicClient([_text_block("part one "), _text_block("part two")])
    backend = AnthropicBackend(PROVIDERS["anthropic"], api_key="sk-test", client=client)
    assert backend.chat(Role.DISCUSSION, "s", "u") == "part one part two"
    assert "tools" not in client.messages.calls[0]


# ----------------------------------------------------------- model selection


def test_the_model_can_be_overridden_globally_and_per_role(monkeypatch):
    monkeypatch.setenv("DOJO_MODEL", "global-model")
    assert role_model(Role.TUTOR) == "global-model"
    monkeypatch.setenv("DOJO_MODEL_AUDITOR", "cheap-model")
    assert role_model(Role.AUDITOR) == "cheap-model"
    assert role_model(Role.REVIEWER) == "global-model"


def test_the_role_model_reaches_the_request(monkeypatch):
    monkeypatch.setenv("DOJO_MODEL_AUDITOR", "cheap-audit-model")
    client = FakeOpenAIClient('{"rating": 1}')
    backend = OpenAICompatBackend(PROVIDERS["deepseek"], api_key="sk-test", client=client)
    backend.chat_json(Role.AUDITOR, "s", "u")
    assert client.completions.calls[0]["model"] == "cheap-audit-model"


# --------------------------------------------------------------- identity


def test_a_backend_can_say_who_it_is():
    """`identity()` is what lands in `attempts.ai_provenance`, so a row can
    never again be mistaken for a live one (or the reverse)."""
    assert MockBackend().identity() == {"backend": "mock", "model": "mock"}
    backend = OpenAICompatBackend(
        PROVIDERS["openai"], api_key="sk-test", client=FakeOpenAIClient("{}")
    )
    identity = backend.identity()
    assert identity["backend"] == "openai"
    assert identity["model"]


# ------------------------------------------------------- tolerant parsing


@pytest.mark.parametrize(
    "content",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Here you go:\n{"a": 1}\nHope that helps!',
    ],
)
def test_json_tolerance_across_providers(content):
    assert parse_json_content(content) == {"a": 1}


def test_a_response_with_no_json_is_an_error_not_an_exception():
    assert parse_json_content("no object here")["error"]
    assert parse_json_content("")["error"]


# ------------------------------------------- bounded requests (v0.13 follow-up)
# The SDK default is a 600-second read timeout with two retries. Against a
# connection that opens and never answers (captive portal, dropped VPN) that is
# up to half an hour of a frozen terminal for one hint — measured at >600 s for a
# single call. Every request now carries its role's bound, and the client is
# built with one retry instead of the SDK's two.


def test_the_interactive_roles_are_bounded_tighter_than_the_long_ones():
    from dojo.tutor.backend import INTERACTIVE_TIMEOUT, LONG_TIMEOUT

    # A student is watching the cursor for these three.
    for role in (Role.TUTOR, Role.DISCUSSION, Role.AUDITOR):
        assert budget_for(role).timeout == INTERACTIVE_TIMEOUT
    # The long-form work happens outside the back-and-forth.
    for role in (Role.REVIEWER, Role.CURATOR, Role.CURATION_AUDITOR, Role.REFERENCER, Role.TEACHER):
        assert budget_for(role).timeout == LONG_TIMEOUT
    # Both tiers stay far below the SDK default that caused the freeze.
    assert LONG_TIMEOUT < 600 and INTERACTIVE_TIMEOUT < LONG_TIMEOUT


def test_every_role_has_a_timeout_and_an_unknown_role_fails_loudly():
    for role in Role:
        assert budget_for(role).timeout > 0
    # Roles are the routing key: a typo must not silently inherit a budget.
    with pytest.raises(ValueError):
        budget_for("not-a-role")


def test_dojo_timeout_overrides_every_role(monkeypatch):
    monkeypatch.setenv("DOJO_TIMEOUT", "42")
    assert budget_for(Role.TUTOR).timeout == 42.0
    assert budget_for(Role.REVIEWER).timeout == 42.0
    # The rest of the budget is untouched.
    assert budget_for(Role.AUDITOR).max_tokens == 128


def test_a_typo_in_dojo_timeout_cannot_end_a_session(monkeypatch):
    from dojo.config import timeout_override

    for bad in ("banana", "", "0", "-5", " "):
        monkeypatch.setenv("DOJO_TIMEOUT", bad)
        assert timeout_override() is None
        assert budget_for(Role.TUTOR).timeout > 0     # the per-role default stands
    monkeypatch.delenv("DOJO_TIMEOUT")
    assert timeout_override() is None


def test_the_openai_request_carries_the_role_timeout():
    client = FakeOpenAIClient('{"ok": true}')
    backend = OpenAICompatBackend(PROVIDERS["deepseek"], api_key="sk-test", client=client)
    backend.chat(Role.TUTOR, "s", "u")
    backend.chat(Role.REVIEWER, "s", "u")
    assert client.completions.calls[0]["timeout"] == budget_for(Role.TUTOR).timeout
    assert client.completions.calls[1]["timeout"] == budget_for(Role.REVIEWER).timeout


def test_the_anthropic_request_carries_the_role_timeout():
    client = FakeAnthropicClient([_text_block("hi")])
    backend = AnthropicBackend(PROVIDERS["anthropic"], api_key="sk-test", client=client)
    backend.chat(Role.TUTOR, "s", "u")
    assert client.messages.calls[0]["timeout"] == budget_for(Role.TUTOR).timeout


def test_the_live_clients_are_built_with_one_retry(monkeypatch):
    """Injected clients (tests) never see this, so it needs its own pin: the
    retry count is what multiplies a stalled wait."""
    from dojo.tutor.backend import REQUEST_RETRIES

    assert REQUEST_RETRIES == 1
    seen: list[dict] = []

    class Recorder:
        def __init__(self, **kwargs):
            seen.append(kwargs)

    monkeypatch.setattr("openai.OpenAI", Recorder)
    OpenAICompatBackend(PROVIDERS["deepseek"], api_key="sk-test")
    monkeypatch.setattr("anthropic.Anthropic", Recorder)
    AnthropicBackend(PROVIDERS["anthropic"], api_key="sk-test")

    assert [call["max_retries"] for call in seen] == [REQUEST_RETRIES, REQUEST_RETRIES]
    assert seen[0]["base_url"] == PROVIDERS["deepseek"].base_url
