"""Tutor + reviewer facade."""

from dojo.tutor.backend import (
    AIBackend,
    AnthropicBackend,
    MockBackend,
    OpenAICompatBackend,
    Role,
    build_backend,
    get_backend,
)
from dojo.tutor.reviewer import review
from dojo.tutor.tutor import TIER_NAMES, HintResult, ask_tutor, de_markdown

__all__ = [
    "AIBackend",
    "AnthropicBackend",
    "OpenAICompatBackend",
    "Role",
    "build_backend",
    "HintResult",
    "MockBackend",
    "TIER_NAMES",
    "ask_tutor",
    "de_markdown",
    "get_backend",
    "review",
]
