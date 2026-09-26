"""One exception boundary for everything that can fail transiently.

A session must never end in a traceback because an API call blipped, a
subprocess fell over, or the network was away. `cli.main` catches only
`KeyboardInterrupt`, so every AI and subprocess call site needed its own
try/except — two of eleven had one (v0.13 audit, S1.5). Usage:

    with guard(console, "the tutor") as g:
        g.value = ask_tutor(...)
    if not g.ok:
        return          # the session carries on; the student was told why

The failure is printed in one line, the full detail goes to the debug log
(`event: "degraded"`), and `g.error` carries the message for a caller that wants
to react. Exceptions the *student* caused are not the target: this is for the
things outside the session's control, and it deliberately does not swallow
`KeyboardInterrupt`.

**Network failures are their own case** (v0.13 follow-up). "the tutor unavailable
(APIConnectionError: Connection error.)" is a true statement that helps nobody:
the class name is not something a student can act on, and a dropped wifi reads
to them as a bug in dojo. `is_network_error` separates a service dojo could not
*reach* (or that stopped answering) from a service that *answered* — 401 (wrong
key), 429 (quota), 5xx — and only the former becomes the plain-language line ("is
the network connection ok?"). The distinction is the honesty contract applied to
error messages: never send someone to check their router over a problem their API
key has.
"""

from __future__ import annotations

import errno
import socket
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from dojo import debuglog

#: What a student sees when dojo cannot reach a service, or the service stopped
#: answering. One template, two nouns: the AI backend during a session, LeetCode
#: in the fetcher.
_NETWORK_MESSAGE = (
    "I'm having trouble connecting to {what} — is the network connection ok?"
)


def network_message(what: str = "the AI backend") -> str:
    """The plain-language line for a network failure."""
    return _NETWORK_MESSAGE.format(what=what)


#: Error class names that mean "could not reach the service, or it stopped
#: answering". Matched by *name* rather than by isinstance on purpose:
#: classifying a failure must not require importing openai/anthropic/httpx
#: (heavy, lazily loaded, and absent under `DOJO_AI_BACKEND=mock`), and every one
#: of these libraries names its transport errors consistently.
_NETWORK_NAMES = frozenset(
    {
        # openai / anthropic SDKs
        "APIConnectionError",
        "APITimeoutError",
        # httpx / httpcore
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "RemoteProtocolError",
        "NetworkError",
        "ProxyError",
        # urllib / urllib3 (the fetcher, and anything built on it)
        "URLError",
        "MaxRetryError",
        "NewConnectionError",
    }
)

#: Names that mean the service **answered** with an error status. These must
#: never be reported as a network problem: telling a student to check their wifi
#: when the API key is wrong (401) or the quota is spent (429) sends them looking
#: in the wrong place.
_ANSWERED_NAMES = frozenset(
    {
        "APIStatusError",
        "APIResponseValidationError",
        "AuthenticationError",
        "PermissionDeniedError",
        "NotFoundError",
        "ConflictError",
        "UnprocessableEntityError",
        "RateLimitError",
        "BadRequestError",
        "InternalServerError",
        "HTTPStatusError",
    }
)

#: errno values that only a network can produce. `EHOSTUNREACH`/`ENETUNREACH` are
#: the "no wifi" case; the rest are dropped connections mid-request.
_NETWORK_ERRNOS = frozenset(
    {
        errno.ENETUNREACH,
        errno.ENETDOWN,
        errno.ENETRESET,
        errno.EHOSTUNREACH,
        errno.EHOSTDOWN,
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.ECONNABORTED,
        errno.EPIPE,
        errno.ETIMEDOUT,
    }
)

#: Exceptions from these modules are about the wire itself.
_NETWORK_MODULES = frozenset({"socket", "ssl"})


def _is_network_shaped(exc: BaseException) -> bool:
    if isinstance(exc, socket.gaierror):  # the name could not be resolved
        return True
    if isinstance(exc, ConnectionError):  # refused / reset / aborted / broken pipe
        return True
    if type(exc).__module__ in _NETWORK_MODULES:
        return True
    if isinstance(exc, TimeoutError):
        # `socket.timeout` IS `TimeoutError` since 3.10 and reports module
        # "builtins", so this is how a stalled connection is caught. Nothing in
        # dojo raises a bare TimeoutError — a subprocess timeout is
        # `subprocess.TimeoutExpired`, a `SubprocessError` that never matches.
        return True
    if isinstance(exc, OSError) and exc.errno in _NETWORK_ERRNOS:
        return True
    return type(exc).__name__ in _NETWORK_NAMES


def is_network_error(exc: BaseException | None) -> bool:
    """Whether a failure is about *reaching* a service (or waiting on it), rather
    than about the service refusing the request.

    The whole cause chain is inspected: the SDKs raise a wrapper whose
    ``__cause__`` is the httpx error whose ``__cause__`` is the socket error, and
    any level may be the informative one. A status answer (401/429/5xx) anywhere
    in the chain wins, so a bad key is never reported as a network problem.
    """
    if exc is None:
        return False
    seen: set[int] = set()
    chain: list[BaseException] = []
    queue: list[BaseException | None] = [exc]
    while queue:
        current = queue.pop(0)  # breadth-first: outermost first, so it reads naturally
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        queue.append(current.__cause__)
        queue.append(current.__context__)
        group = getattr(current, "exceptions", None)  # ExceptionGroup (3.11+)
        if isinstance(group, tuple):
            queue.extend(group)
    if any(type(item).__name__ in _ANSWERED_NAMES for item in chain):
        return False
    return any(_is_network_shaped(item) for item in chain)


@dataclass
class Guarded:
    ok: bool = True
    error: str | None = None
    value: Any = None
    detail: dict = field(default_factory=dict)
    #: True when the failure was the network: the caller may want to phrase its
    #: own follow-up ("nothing was recorded — try again when you're back online")
    #: rather than repeating a technical cause the student cannot use.
    network: bool = False


@contextmanager
def guard(console, label: str, guidance: str | None = None):
    """Run a block that may fail without taking the session down.

    ``label`` names the thing in the student's terms ("the tutor", "the scale
    probe", "the reviewer") — the message says what did not happen, never a
    traceback. ``guidance`` is an optional next step ("carrying on without a
    measurement")."""
    box = Guarded()
    try:
        yield box
    except Exception as exc:  # noqa: BLE001 - the whole point of this module
        box.ok = False
        box.error = f"{type(exc).__name__}: {exc}"
        box.network = is_network_error(exc)
        try:
            debuglog.log_event(
                {
                    "event": "degraded",
                    "label": label,
                    "error": box.error,
                    "network": box.network,
                }
            )
        except Exception:  # noqa: BLE001 - logging must never be the failure
            pass
        if box.network:
            # Two lines, and neither of them names an exception class: there is
            # nothing here for the student to act on except their connection.
            console.print(f"[yellow]{network_message()}[/yellow]")
            tail = guidance or "carrying on."
            console.print(f"[dim]{label} didn't answer — {tail}[/dim]")
            return
        tail = f" — {guidance}" if guidance else " — carrying on."
        console.print(f"[yellow]{label} unavailable ({box.error}){tail}[/yellow]")
