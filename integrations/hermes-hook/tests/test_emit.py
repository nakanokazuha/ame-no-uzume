"""Unit tests for the standalone Hermes shell-hook emitter."""

import importlib
import json
import socket
import subprocess
import sys
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
from threading import Thread
from types import ModuleType
from typing import IO, Any, Protocol, cast
from urllib.error import HTTPError
from urllib.request import Request

import pytest

_HERMES_TOP_LEVEL_PAYLOAD_KEYS = {
    "tool_name",
    "args",
    "session_id",
    "parent_session_id",
}
_HERMES_STOP_TEST_DEFAULTS: dict[str, object] = {
    "parent_session_id": "parent-sess",
    "child_role": None,
    "child_summary": "Synthetic summary for hooks test",
    "child_status": "completed",
    "duration_ms": 1234,
}


class RedirectHandler(Protocol):
    """Minimal typed surface used to prove the opener cannot follow redirects."""

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None: ...


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

    class Opener:
        def open(self, request: Any, *, timeout: float) -> Response:
            sent.update(json.loads(request.data.decode("utf-8")))
            sent["url"] = request.full_url
            sent["headers"] = dict(request.header_items())
            sent["timeout"] = timeout
            return Response()

    monkeypatch.setattr(emitter, "build_opener", lambda *_: Opener())
    return sent


def configure_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "YUME_HOOK_URL", "http://127.0.0.1:8000/api/integrations/hermes/events"
    )
    monkeypatch.setenv("YUME_HOOK_TOKEN", "hook-secret")


def hermes_test_stop_payload(fixture_path: Path) -> dict[str, object]:
    """Build the stdin shape Hermes 0.18.2 gives a configured stop hook."""
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(fixture, dict)
    hook_kwargs = {**_HERMES_STOP_TEST_DEFAULTS, **fixture}
    return {
        "session_id": hook_kwargs.get("session_id")
        or hook_kwargs.get("parent_session_id")
        or "",
        "extra": {
            key: value
            for key, value in hook_kwargs.items()
            if key not in _HERMES_TOP_LEVEL_PAYLOAD_KEYS
        },
    }


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
                "child_session_id": "child-session-7",
                "child_subagent_id": "child-7",
                "child_role": "researcher",
                "child_goal": "Compare hooks",
                "api_key": "must-not-leak",
            },
        },
    )

    assert result == {}
    assert sent["extra"] == {
        "child_session_id": "child-session-7",
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


def test_native_subagent_lifecycle_prefers_the_shared_child_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native Hermes stops omit child_subagent_id but retain child_session_id."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    sent = capture_request(monkeypatch, emitter)

    emitter.emit(
        "subagent_stop",
        {
            "session_id": "parent-1",
            "extra": {
                "child_session_id": "child-session-7",
                "child_status": "completed",
            },
        },
    )

    assert sent["extra"] == {
        "child_session_id": "child-session-7",
        "child_status": "completed",
    }


def test_stop_fixture_reaches_emitter_with_native_worker_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented diagnostic must use the same kwargs-to-stdin path as Hermes."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    sent = capture_request(monkeypatch, emitter)
    fixture_path = Path(__file__).parent / "fixtures" / "stop.json"

    payload = hermes_test_stop_payload(fixture_path)
    emitter.emit("subagent_stop", payload)

    assert sent["session_id"] == "parent-session-1"
    assert sent["extra"]["child_session_id"] == "child-session-7"
    assert sent["extra"]["child_status"] == "completed"


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

    class FailingOpener:
        def open(self, *_: object, **__: object) -> object:
            return reset_connection()

    monkeypatch.setattr(emitter, "build_opener", lambda *_: FailingOpener())

    assert emitter.emit("subagent_start", {"session_id": "parent-1", "extra": {}}) == {}


@pytest.mark.parametrize(
    "hook_url",
    [
        "https://127.0.0.1:8000/api/integrations/hermes/events",
        "http://localhost:8000/api/integrations/hermes/events",
        "http://192.0.2.1:8000/api/integrations/hermes/events",
        "http://127.0.0.1:invalid/api/integrations/hermes/events",
        "http://user:password@127.0.0.1:8000/api/integrations/hermes/events",
    ],
)
def test_emit_rejects_non_loopback_or_malformed_destinations_before_sending(
    monkeypatch: pytest.MonkeyPatch, hook_url: str
) -> None:
    """A malformed destination must never receive the hook bearer token."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    monkeypatch.setenv("YUME_HOOK_URL", hook_url)
    sent = False

    def unexpected_transport(*_: object, **__: object) -> object:
        nonlocal sent
        sent = True
        raise AssertionError("invalid hook URL reached the transport")

    monkeypatch.setattr(emitter, "build_opener", unexpected_transport)

    assert emitter.emit("subagent_start", {"session_id": "parent-1", "extra": {}}) == {}
    assert sent is False


def test_emit_disables_proxy_transport_even_when_proxy_environment_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit no-proxy transport keeps the bearer credential on loopback."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    monkeypatch.setenv("http_proxy", "http://198.51.100.1:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://198.51.100.1:8080")
    monkeypatch.setenv("https_proxy", "http://198.51.100.1:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://198.51.100.1:8080")
    handlers: tuple[object, ...] = ()
    requests: list[Request] = []

    class Response:
        def close(self) -> None:
            return None

    class LoopbackOpener:
        def open(self, request: Request, *, timeout: float) -> Response:
            requests.append(request)
            return Response()

    def capture_opener(*configured_handlers: object) -> LoopbackOpener:
        nonlocal handlers
        handlers = configured_handlers
        return LoopbackOpener()

    monkeypatch.setattr(emitter, "build_opener", capture_opener)

    assert emitter.emit("subagent_start", {"session_id": "parent-1", "extra": {}}) == {}
    proxy_handler = next(
        handler for handler in handlers if isinstance(handler, emitter.ProxyHandler)
    )

    assert proxy_handler.proxies == {}
    assert [request.full_url for request in requests] == [
        "http://127.0.0.1:8000/api/integrations/hermes/events"
    ]
    assert requests[0].get_header("Authorization") == "Bearer hook-secret"


def test_emit_does_not_follow_a_redirect_or_replay_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect is rejected on the emitter request path before a second send."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    requests: list[Request] = []

    class RedirectingOpener:
        def __init__(self, no_redirect_handler: object) -> None:
            self._no_redirect_handler = cast(RedirectHandler, no_redirect_handler)

        def open(self, request: Request, *, timeout: float) -> object:
            requests.append(request)
            redirected_request = self._no_redirect_handler.redirect_request(
                request,
                BytesIO(),
                302,
                "Found",
                HTTPMessage(),
                "http://127.0.0.1:9000/second-target",
            )
            if redirected_request is not None:
                requests.append(redirected_request)
            raise HTTPError(request.full_url, 302, "Found", HTTPMessage(), None)

    def redirecting_opener(*handlers: object) -> RedirectingOpener:
        no_redirect_handler = next(
            handler
            for handler in handlers
            if isinstance(handler, emitter.NoRedirectHandler)
        )
        return RedirectingOpener(no_redirect_handler)

    monkeypatch.setattr(emitter, "build_opener", redirecting_opener)

    assert emitter.emit("subagent_start", {"session_id": "parent-1", "extra": {}}) == {}
    assert [request.full_url for request in requests] == [
        "http://127.0.0.1:8000/api/integrations/hermes/events"
    ]
    assert requests[0].get_header("Authorization") == "Bearer hook-secret"


@pytest.mark.parametrize(
    "hook_url",
    [
        "http://127.0.0.0:8000/api/integrations/hermes/events",
        "http://127.255.255.255:8000/api/integrations/hermes/events",
        "http://[::1]:8000/api/integrations/hermes/events",
    ],
)
def test_emit_accepts_literal_loopback_destinations(
    monkeypatch: pytest.MonkeyPatch, hook_url: str
) -> None:
    """The bridge supports the full IPv4 loopback block and IPv6 loopback."""
    emitter = load_emitter(monkeypatch)
    configure_hook(monkeypatch)
    monkeypatch.setenv("YUME_HOOK_URL", hook_url)
    sent = capture_request(monkeypatch, emitter)

    emitter.emit("subagent_start", {"session_id": "parent-1", "extra": {}})

    assert sent["url"] == hook_url


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
