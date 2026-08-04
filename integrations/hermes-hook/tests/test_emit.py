"""Unit tests for the standalone Hermes shell-hook emitter."""

import importlib
import json
import socket
import subprocess
import sys
from pathlib import Path
from threading import Thread
from types import ModuleType
from typing import Any

import pytest


def load_emitter(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the standalone emitter after giving each test a clean module."""
    module_directory = __file__.removesuffix("/tests/test_emit.py")
    monkeypatch.syspath_prepend(module_directory)
    sys.modules.pop("emit", None)
    return importlib.import_module("emit")


def capture_request(
    monkeypatch: pytest.MonkeyPatch, emitter: ModuleType
) -> dict[str, Any]:
    """Capture the serialized event at the HTTP boundary without network I/O."""
    sent: dict[str, Any] = {}

    class Response:
        def close(self) -> None:
            return None

    def fake_urlopen(request: Any, *, timeout: float) -> Response:
        sent.update(json.loads(request.data.decode("utf-8")))
        sent["url"] = request.full_url
        sent["headers"] = dict(request.header_items())
        sent["timeout"] = timeout
        return Response()

    monkeypatch.setattr(emitter, "urlopen", fake_urlopen)
    return sent


def configure_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "YUME_HOOK_URL", "http://127.0.0.1:8000/api/integrations/hermes/events"
    )
    monkeypatch.setenv("YUME_HOOK_TOKEN", "hook-secret")


def test_subagent_start_payload_is_minimal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dropping the allow-list would leak the hook API key to the dashboard."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    sent = capture_request(monkeypatch, emitter)

    result = emitter.emit(
        "subagent_start",
        {
            "session_id": "parent-1",
            "extra": {
                "child_subagent_id": "child-7",
                "child_role": "researcher",
                "child_goal": "Compare hooks",
                "api_key": "must-not-leak",
            },
        },
    )

    assert result == {}
    assert sent["extra"] == {
        "child_subagent_id": "child-7",
        "child_role": "researcher",
        "child_goal": "Compare hooks",
    }
    assert sent["session_id"] == "parent-1"
    assert sent["event"] == "subagent_start"
    assert sent["url"] == "http://127.0.0.1:8000/api/integrations/hermes/events"
    assert sent["headers"]["Authorization"] == "Bearer hook-secret"
    assert sent["timeout"] == 1


def test_subagent_stop_removes_raw_tool_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forwarding a raw tool result would violate the bridge privacy contract."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    sent = capture_request(monkeypatch, emitter)

    emitter.emit(
        "subagent_stop",
        {
            "session_id": "parent-1",
            "extra": {
                "child_subagent_id": "child-7",
                "child_role": "researcher",
                "child_status": "completed",
                "duration_ms": 125,
                "tool_call_history": [
                    {
                        "tool_name": "web.search",
                        "status": "completed",
                        "result": "credential-bearing raw result",
                        "summary": "unapproved child summary",
                    }
                ],
            },
        },
    )

    assert sent["extra"] == {
        "child_subagent_id": "child-7",
        "child_role": "researcher",
        "child_status": "completed",
        "duration_ms": 125,
        "tool_call_history": [{"tool_name": "web.search", "status": "completed"}],
    }


def test_subagent_stop_drops_nested_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nested values in allowed fields must not cross the HTTP boundary."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    sent = capture_request(monkeypatch, emitter)

    emitter.emit(
        "subagent_stop",
        {
            "session_id": {"api_key": "nested-session-marker"},
            "extra": {
                "child_subagent_id": "child-7",
                "child_role": {"api_key": "nested-role-marker"},
                "child_status": "completed",
                "duration_ms": {"raw_tool_result": "nested-duration-marker"},
                "tool_call_history": [
                    {
                        "tool_name": {"api_key": "nested-tool-marker"},
                        "status": ["raw-tool-result"],
                    },
                    {"tool_name": "web.search", "status": "completed"},
                ],
            },
        },
    )

    assert sent["session_id"] == ""
    assert sent["extra"] == {
        "child_subagent_id": "child-7",
        "child_status": "completed",
        "tool_call_history": [{"tool_name": "web.search", "status": "completed"}],
    }
    assert "nested-" not in json.dumps(sent)


def test_emit_returns_empty_when_transport_drops_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reset while sending telemetry must not raise into the Hermes hook."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)

    def reset_connection(*_: object, **__: object) -> object:
        raise ConnectionResetError("connection reset")

    monkeypatch.setattr(emitter, "urlopen", reset_connection)

    assert emitter.emit("subagent_start", {"session_id": "parent-1", "extra": {}}) == {}


def test_cli_returns_empty_json_when_loopback_peer_drops_connection() -> None:
    """A transport failure exits successfully with the exact hook response."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def drop_connection() -> None:
        connection, _ = listener.accept()
        connection.close()
        listener.close()

    worker = Thread(target=drop_connection)
    worker.start()
    emitter_path = Path(__file__).parents[1] / "emit.py"
    completed = subprocess.run(
        [sys.executable, str(emitter_path), "subagent_start"],
        input=b'{"session_id": "parent-1", "extra": {}}',
        capture_output=True,
        check=False,
        env={
            "YUME_HOOK_URL": f"http://127.0.0.1:{port}/api/integrations/hermes/events",
            "YUME_HOOK_TOKEN": "hook-secret",
        },
    )
    worker.join(timeout=1)

    assert completed.returncode == 0
    assert completed.stdout == b"{}\n"
    assert completed.stderr == b""
