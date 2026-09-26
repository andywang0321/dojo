"""The exception boundary, and the network/answered distinction inside it.

A dropped connection used to reach a student as "the tutor unavailable
(APIConnectionError: Connection error.)" — a true statement that helps nobody:
the class name is not actionable, and their own wifi reading as a dojo bug is
what "dojo crashes when I'm offline" meant (v0.13 follow-up). What must *not*
change is the other direction: a 401 (wrong key) or a 429 (quota) is the service
answering, and sending that student to check their router is a wrong trail.
"""

from __future__ import annotations

import errno
import socket
import ssl
import subprocess
import urllib.error

import pytest

from dojo.guard import (
    Guarded,
    guard,
    is_network_error,
    network_message,
)


class Recorder:
    """The smallest console `guard` can print to."""

    def __init__(self):
        self.out: list[str] = []

    def print(self, *args, **kwargs):
        self.out.append(" ".join(str(a) for a in args))

    @property
    def text(self) -> str:
        return "\n".join(self.out)


def _instance(path: str):
    """A real exception object from a real library, without constructing a
    request (which would need the SDK's httpx, and this must stay offline)."""
    module_name, _, class_name = path.rpartition(".")
    module = __import__(module_name, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cls.__new__(cls)


def _transport_instance(path: str):
    """Same, for the SDK's *transport* library (`openai` 3.8 ships `httpx2`).
    A future openai may swap it; the name-matched contract is what matters, so a
    missing module skips rather than failing."""
    try:
        return _instance(path)
    except ImportError:  # pragma: no cover - depends on the SDK's transport
        pytest.skip(f"{path} is not installed in this environment")


# ------------------------------------------------------- what counts as network


@pytest.mark.parametrize(
    "exc",
    [
        # The stdlib, which is what everything else wraps.
        socket.gaierror(-2, "Name or service not known"),   # no DNS = no wifi
        ConnectionRefusedError(errno.ECONNREFUSED, "refused"),
        ConnectionResetError(errno.ECONNRESET, "reset"),
        ConnectionAbortedError(errno.ECONNABORTED, "aborted"),
        BrokenPipeError(errno.EPIPE, "broken pipe"),
        OSError(errno.ENETUNREACH, "Network is unreachable"),
        OSError(errno.EHOSTUNREACH, "No route to host"),
        TimeoutError("timed out"),                          # socket.timeout is this
        ssl.SSLError("certificate verify failed"),
        urllib.error.URLError("no route"),
        # The SDKs and their transports, matched by name so that classifying a
        # failure never imports them.
        _instance("openai.APIConnectionError"),
        _instance("openai.APITimeoutError"),
        _instance("anthropic.APIConnectionError"),
        _instance("anthropic.APITimeoutError"),
        _transport_instance("httpx2.ConnectError"),
        _transport_instance("httpx2.ReadTimeout"),
        _transport_instance("httpx2.ConnectTimeout"),
        _transport_instance("httpcore2.ConnectError"),
    ],
)
def test_unreachable_and_stalled_are_network_failures(exc):
    assert is_network_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        # The service answered. Every one of these is actionable as itself.
        _instance("openai.AuthenticationError"),
        _instance("openai.PermissionDeniedError"),
        _instance("openai.RateLimitError"),
        _instance("openai.BadRequestError"),
        _instance("openai.InternalServerError"),
        _instance("openai.APIStatusError"),
        _instance("anthropic.AuthenticationError"),
        _instance("anthropic.RateLimitError"),
        # Nothing to do with the network at all.
        ValueError("bad value"),
        KeyError("missing"),
        RuntimeError("DEEPSEEK_API_KEY is not set"),
        # A subprocess timeout is *not* a stalled connection: dojo's own probe
        # and judge use it, and calling that "check your network" would be a lie.
        subprocess.TimeoutExpired(["python", "-c", "pass"], 5),
    ],
)
def test_an_answer_or_a_bug_is_not_a_network_failure(exc):
    assert is_network_error(exc) is False


def test_the_whole_cause_chain_is_inspected():
    """The real shape: openai.APIConnectionError → httpx2.ConnectError →
    httpcore2.ConnectError → ConnectionRefusedError. Any level may be the
    informative one, and the outermost SDK wrapper is not network-named in every
    library dojo might add."""
    outer = RuntimeError("the backend failed")           # e.g. a wrapper we add
    middle = _instance("openai.APIConnectionError")
    middle.__cause__ = _transport_instance("httpx2.ConnectError")
    outer.__cause__ = middle
    assert is_network_error(outer) is True


def test_a_status_error_wins_over_an_inner_transport_cause():
    """A 401 with a connection-ish cause is still a 401: the key is wrong."""
    auth = _instance("openai.AuthenticationError")
    auth.__cause__ = ConnectionRefusedError(errno.ECONNREFUSED, "refused")
    assert is_network_error(auth) is False


def test_exception_groups_are_searched():
    group = ExceptionGroup("calls failed", [ValueError("x"), ConnectionResetError("reset")])
    assert is_network_error(group) is True


def test_none_is_not_a_network_failure():
    assert is_network_error(None) is False


def test_the_message_names_the_service():
    assert network_message() == (
        "I'm having trouble connecting to the AI backend — is the network connection ok?"
    )
    assert network_message("LeetCode") == (
        "I'm having trouble connecting to LeetCode — is the network connection ok?"
    )


# ------------------------------------------------------------- the guard itself


def test_a_network_failure_is_reported_in_plain_language():
    console = Recorder()
    with guard(console, "the tutor", "ask again in a moment") as g:
        raise _instance("openai.APIConnectionError")
    assert g.ok is False
    assert g.network is True
    assert network_message() in console.text
    assert "the tutor didn't answer — ask again in a moment" in console.text
    # No exception class, no "unavailable": nothing here is the student's to debug.
    assert "APIConnectionError" not in console.text
    assert "unavailable" not in console.text


def test_a_network_failure_without_guidance_still_says_carrying_on():
    console = Recorder()
    with guard(console, "the scale probe") as g:
        raise TimeoutError("stalled")
    assert g.network is True
    assert "the scale probe didn't answer — carrying on." in console.text


def test_a_non_network_failure_keeps_its_technical_line():
    console = Recorder()
    with guard(console, "the reviewer", "the attempt is still recorded") as g:
        raise RuntimeError("the JSON was malformed")
    assert g.ok is False
    assert g.network is False
    assert "the reviewer unavailable (RuntimeError: the JSON was malformed)" in console.text
    assert network_message() not in console.text


def test_the_guard_records_the_failure_and_the_student_keeps_going():
    console = Recorder()
    with guard(console, "the tutor", "ask again") as g:
        g.value = "no answer"
        raise ConnectionRefusedError(errno.ECONNREFUSED, "refused")
    assert g.value == "no answer"      # what the block got done before failing
    assert g.error == "ConnectionRefusedError: [Errno 61] refused"
    assert g.network is True


def test_a_healthy_block_is_untouched():
    console = Recorder()
    with guard(console, "the tutor") as g:
        g.value = "an answer"
    assert (g.ok, g.network, g.value) == (True, False, "an answer")
    assert console.text == ""


def test_the_guard_does_not_swallow_a_keyboard_interrupt():
    """Ctrl-C is the student's, not a transient failure (v0.13 contract)."""
    with pytest.raises(KeyboardInterrupt), guard(Recorder(), "the tutor"):
        raise KeyboardInterrupt


def test_guarded_defaults_are_the_healthy_ones():
    box = Guarded()
    assert (box.ok, box.network, box.error, box.value) == (True, False, None, None)
