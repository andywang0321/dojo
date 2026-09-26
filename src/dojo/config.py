"""Central configuration: paths, environment, and the AI provider table.

Nothing here should ever need a network call. The provider is chosen by
``DOJO_AI_BACKEND`` / ``DOJO_PROVIDER`` (``mock``, ``deepseek``, ``openai``,
``anthropic``; default ``deepseek``) so the whole pipeline is exercisable
without an API key, and each provider's key comes from its own env var or the
gitignored dotenv — never from a prompt or a log.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
#: Authored content that ships with the repo and is expected to be read-only at
#: runtime: the roadmap, the curation overrides, the seed corpus.
CONTENT_DIR = REPO_ROOT / "data"
#: User state: the database, the debug log, the active-user conf. Separated from
#: CONTENT_DIR so tests (and a future second checkout) can redirect state without
#: losing the content beside it — `DOJO_DATA_DIR` moves this and nothing else.
DATA_DIR = Path(os.environ.get("DOJO_DATA_DIR", str(CONTENT_DIR)))
#: dojo's own Python (the uv-managed venv) — workbench shebangs and the
#: generated IDE config point at this, so editors/debuggers/linters know
#: which interpreter user code belongs to (v0.10.6).
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def _default_workbench() -> Path:
    """Per-user scratch OUTSIDE the repo (v0.10.1): the workbench is where
    VSCode and debugger tooling attach (ipykernel installs, debug state),
    and it must never collide with git or require `git pull --force`."""
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "dojo" / "workbench"


WORKBENCH_DIR = Path(os.environ.get("DOJO_WORKBENCH_DIR", str(_default_workbench())))
PROBLEM_OVERRIDES = CONTENT_DIR / "problem_overrides.json"
#: The seed corpus: one problem per file, prompt in the module docstring,
#: organized by pattern directory (imported by dojo.bank).
PROBLEMS_DIR = REPO_ROOT / "problems"
DB_PATH = DATA_DIR / "dojo.db"
#: Curator provenance + audit reports (gitignored): a proposal and the audit that
#: judged it, kept so a curation decision can be re-read later. User state, so it
#: follows DATA_DIR — `dojo report`/`dojo curate` used to spell out
#: `REPO_ROOT/"data"/…`, which escaped every redirect (and wrote into the real
#: repo from a test run).
CURATION_DIR = DATA_DIR / "curation"
#: Debug log (gitignored): raw AI traffic for post-hoc debugging; cleared on
#: major version bumps (dojo/debuglog.py).
LOGS_DIR = DATA_DIR / "logs"
#: Active-user config (gitignored): {"user": "name"} — one computer, one user.
DOJO_CONF = DATA_DIR / "dojo.conf"


def load_conf(path: Path | None = None) -> dict:
    path = path or DOJO_CONF
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_conf(data: dict, path: Path | None = None) -> None:
    path = path or DOJO_CONF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


@dataclass(frozen=True)
class Provider:
    """One AI provider: where to send the request, which key opens it, and
    which wire format it speaks.

    ``wire`` is the shape of the API, not the brand: DeepSeek and OpenAI both
    speak OpenAI-compatible chat completions (they differ by base URL, model and
    key), while Anthropic's messages API takes the system prompt as a top-level
    field, has no ``response_format``, and returns JSON best via a forced tool
    call. ``json_mode`` names that difference so the backend does not guess."""

    name: str
    model: str
    key_env: str
    base_url: str | None = None
    wire: str = "openai"  # "openai" | "anthropic"
    json_mode: str = "object"  # "object" | "tool" | "prompt"


#: The providers dojo knows how to talk to. `DOJO_MODEL` overrides the model for
#: all of them; `DOJO_MODEL_<ROLE>` overrides it for one role (e.g.
#: `DOJO_MODEL_AUDITOR` for the leak check that runs on every hint).
PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        name="deepseek",
        model="deepseek-chat",
        key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    "openai": Provider(
        name="openai",
        model=os.environ.get("DOJO_OPENAI_MODEL", "gpt-4.1-mini"),
        key_env="OPENAI_API_KEY",
        base_url=None,  # the SDK default
    ),
    "anthropic": Provider(
        name="anthropic",
        model=os.environ.get("DOJO_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        key_env="ANTHROPIC_API_KEY",
        wire="anthropic",
        json_mode="tool",
    ),
}

#: Accepted env var aliases per provider (the DOJO_-prefixed form is for people
#: who keep several keys exported at once).
KEY_ALIASES = {
    "deepseek": ("DEEPSEEK_API_KEY", "DOJO_DEEPSEEK_API_KEY"),
    "openai": ("OPENAI_API_KEY", "DOJO_OPENAI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "DOJO_ANTHROPIC_API_KEY"),
}


def ai_backend() -> str:
    """The configured provider name (default `deepseek`; `mock` for offline)."""
    return os.environ.get("DOJO_AI_BACKEND") or os.environ.get("DOJO_PROVIDER") or "deepseek"


def resolve_key(provider: Provider | str) -> str | None:
    """The API key for a provider: environment (and its aliases) first, then
    the gitignored dotenv. Never logged, never put in a prompt."""
    provider = PROVIDERS[provider] if isinstance(provider, str) else provider
    for name in key_env_names(provider):
        value = os.environ.get(name) or _read_dotenv(name)
        if value:
            return value
    return _read_dotenv(provider.key_env)


def key_env_names(provider: Provider | str) -> tuple[str, ...]:
    """Every environment variable that can hold a provider's key."""
    provider = PROVIDERS[provider] if isinstance(provider, str) else provider
    return tuple(KEY_ALIASES.get(provider.name, (provider.key_env,)))


def deepseek_api_key() -> str | None:
    """Kept for callers that predate the provider table."""
    return resolve_key("deepseek")


def detect_provider_key() -> tuple[str, str] | None:
    """(provider, key) for the first provider with a key available, or None.

    The wizard uses this to skip the prompt; the order is the table's order, so
    a machine with several keys exported gets DeepSeek unless it says otherwise.
    """
    for name in PROVIDERS:
        key = resolve_key(name)
        if key:
            return name, key
    return None


def role_model(role, provider: "Provider | None" = None) -> str:
    """The model for a role: `DOJO_MODEL_<ROLE>` > `DOJO_MODEL` > the provider's
    own default.

    `provider` defaults to the configured one, but an explicit backend passes
    *its* provider — building an OpenAI backend while `DOJO_AI_BACKEND=deepseek`
    must not send DeepSeek's model to OpenAI (v0.13)."""
    role_name = str(getattr(role, "value", role)).upper()
    chosen = provider or PROVIDERS.get(ai_backend())
    default = chosen.model if chosen else "deepseek-chat"
    return (
        os.environ.get(f"DOJO_MODEL_{role_name}")
        or os.environ.get("DOJO_MODEL")
        or default
    )


def timeout_override() -> float | None:
    """`DOJO_TIMEOUT` (seconds): one number for every role, for a provider or a
    model slower than dojo's per-role defaults (v0.13 follow-up).

    Unparseable or non-positive values are ignored rather than fatal: a typo in
    an environment variable must not be the reason a session ends, and the
    per-role default is always a sane bound."""
    raw = os.environ.get("DOJO_TIMEOUT")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _read_dotenv(key: str) -> str | None:
    """Minimal .env reader (no python-dotenv dependency)."""
    dotenv = REPO_ROOT / ".env"
    if not dotenv.exists():
        return None
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip("'\"")
    return None
