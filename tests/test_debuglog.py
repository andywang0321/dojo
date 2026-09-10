"""Debug logging: raw AI traffic, JSONL append, version-bump clearing.

Only DeepSeekBackend logs (MockBackend never writes), and these tests
redirect ``debuglog.LOG_PATH`` onto tmp paths — the real data/logs/ is
never touched.
"""

import json
from types import SimpleNamespace

import pytest

from dojo import debuglog


def test_log_event_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(debuglog, "LOG_PATH", tmp_path / "logs" / "dojo.log")
    debuglog.log_event({"event": "ai", "kind": "chat", "system": "S", "user": "U", "raw": "R"})
    debuglog.log_event({"event": "backend_error", "error": "boom"})

    lines = (tmp_path / "logs" / "dojo.log").read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "ai"
    assert first["raw"] == "R"
    assert "ts" in first  # timestamp attached by the logger
    assert json.loads(lines[1])["event"] == "backend_error"


def test_maybe_clear_on_version_bump(tmp_path, monkeypatch):
    monkeypatch.setattr(debuglog, "LOG_PATH", tmp_path / "logs" / "dojo.log")
    debuglog.log_event({"event": "ai"})  # first use writes the version marker
    assert (tmp_path / "logs" / "dojo.log").exists()

    # same version: nothing cleared
    assert debuglog.maybe_clear_logs(tmp_path / "logs", "0.9") is False
    assert (tmp_path / "logs" / "dojo.log").exists()

    # major version bump: log wiped, marker rewritten
    assert debuglog.maybe_clear_logs(tmp_path / "logs", "0.10") is True
    assert not (tmp_path / "logs" / "dojo.log").exists()
    assert (tmp_path / "logs" / ".version").read_text().strip() == "0.10"


def _live_backend(monkeypatch, tmp_path):
    from dojo.tutor.backend import DeepSeekBackend

    monkeypatch.setattr(debuglog, "LOG_PATH", tmp_path / "logs" / "dojo.log")
    return DeepSeekBackend(api_key="sk-test")  # no network at construction


def _events(tmp_path):
    return [
        json.loads(line)
        for line in (tmp_path / "logs" / "dojo.log").read_text().splitlines()
    ]


def test_backend_logs_raw_chat_json(monkeypatch, tmp_path):
    backend = _live_backend(monkeypatch, tmp_path)
    fake = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"a": 1}'))]
    )
    monkeypatch.setattr(backend._client.chat.completions, "create", lambda **kw: fake)

    assert backend.chat_json("SYS", "USER") == {"a": 1}

    events = _events(tmp_path)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "ai"
    assert event["kind"] == "chat_json"
    assert event["system"] == "SYS"
    assert event["user"] == "USER"
    assert event["raw"] == '{"a": 1}'  # the response before parsing
    assert event["parsed"] == {"a": 1}
    assert "latency_ms" in event


def test_backend_logs_errors_and_reraises(monkeypatch, tmp_path):
    backend = _live_backend(monkeypatch, tmp_path)

    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(backend._client.chat.completions, "create", boom)

    with pytest.raises(RuntimeError, match="boom"):
        backend.chat("SYS", "USER")

    events = _events(tmp_path)
    assert len(events) == 1
    assert events[0]["event"] == "backend_error"
    assert "boom" in events[0]["error"]
    assert events[0]["system"] == "SYS"
