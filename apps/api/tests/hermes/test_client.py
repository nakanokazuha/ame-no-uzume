import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from httpx import Response
from pydantic import ValidationError

from yume_api.contracts.events import ConversationMessage
from yume_api.hermes.client import HermesClient, extract_text
from yume_api.hermes.models import HermesCapabilities
from yume_api.hermes.sse import iter_sse


@pytest.mark.asyncio
@respx.mock
async def test_get_capabilities_sends_bearer_authentication() -> None:
    route = respx.get("http://hermes/v1/capabilities").mock(
        return_value=Response(
            200,
            json={"features": {"session_chat_stream": True, "run_stop": True}},
        )
    )

    async with HermesClient("http://hermes/", "secret") as client:
        capabilities = await client.get_capabilities()

    assert capabilities == HermesCapabilities(session_chat_stream=True, run_stop=True)
    assert route.called
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
@respx.mock
async def test_get_capabilities_rejects_malformed_features() -> None:
    respx.get("http://hermes/v1/capabilities").mock(
        return_value=Response(200, json={"features": {"run_stop": "yes"}})
    )

    async with HermesClient("http://hermes", "secret") as client:
        with pytest.raises(ValidationError):
            await client.get_capabilities()


@pytest.mark.asyncio
@respx.mock
async def test_create_session_posts_the_dashboard_title() -> None:
    route = respx.post("http://hermes/api/sessions").mock(
        return_value=Response(201, json={"id": "session-1"})
    )

    async with HermesClient("http://hermes", "secret") as client:
        session_id = await client.create_session("Yume Dashboard")

    assert session_id == "session-1"
    assert json.loads(route.calls.last.request.content) == {"title": "Yume Dashboard"}


@pytest.mark.asyncio
@respx.mock
async def test_stream_session_chat_parses_sse_frames() -> None:
    respx.post("http://hermes/api/sessions/session-1/chat/stream").mock(
        return_value=Response(
            200,
            content=(
                b"event: assistant.delta\n"
                b'data: {"text":"Hel"}\n'
                b"\n"
                b"event: assistant.completed\n"
                b'data: {"message_id":"m2"}\n'
                b"\n"
            ),
        )
    )

    async with HermesClient("http://hermes", "secret") as client:
        events = [event async for event in client.stream_session_chat("session-1", "Hello")]

    assert [(event.event, event.data) for event in events] == [
        ("assistant.delta", {"text": "Hel"}),
        ("assistant.completed", {"message_id": "m2"}),
    ]


@pytest.mark.asyncio
@respx.mock
async def test_get_session_messages_extracts_supported_text_content() -> None:
    respx.get("http://hermes/api/sessions/session-1/messages").mock(
        return_value=Response(
            200,
            json=[
                {"id": "m1", "role": "user", "content": "Hello"},
                {
                    "id": "m2",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Hello "},
                        {"type": "tool_call", "name": "search"},
                        {"type": "text", "text": "back"},
                    ],
                },
                {"id": "m3", "role": "system", "content": "Ignore me"},
            ],
        )
    )

    async with HermesClient("http://hermes", "secret") as client:
        messages = await client.get_session_messages("session-1")

    assert messages == [
        ConversationMessage(message_id="m1", role="user", text="Hello"),
        ConversationMessage(message_id="m2", role="assistant", text="Hello back"),
    ]


@pytest.mark.asyncio
@respx.mock
async def test_get_session_messages_ignores_unsupported_role_content() -> None:
    respx.get("http://hermes/api/sessions/session-1/messages").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": "tool-1",
                    "role": "tool",
                    "content": {"result": "not conversation text"},
                },
                {"id": "m1", "role": "assistant", "content": "Ready"},
            ],
        )
    )

    async with HermesClient("http://hermes", "secret") as client:
        messages = await client.get_session_messages("session-1")

    assert messages == [ConversationMessage(message_id="m1", role="assistant", text="Ready")]


@pytest.mark.asyncio
@respx.mock
async def test_task_uses_runs_sse_when_session_stream_is_absent() -> None:
    create_route = respx.post("http://hermes/v1/runs").mock(
        return_value=Response(201, json={"run_id": "run-1"})
    )
    respx.get("http://hermes/v1/runs/run-1/events").mock(
        return_value=Response(
            200,
            content=b'event: run.completed\ndata: {"run_id":"run-1"}\n\n',
        )
    )
    capabilities = HermesCapabilities(
        run_submission=True,
        run_status=True,
        run_events_sse=True,
    )

    async with HermesClient("http://hermes", "secret") as client:
        events = [
            event
            async for event in client.stream_task(
                capabilities,
                "session-1",
                "Research hooks",
                [ConversationMessage(message_id="m1", role="assistant", text="Ready")],
            )
        ]

    assert events[-1].event == "run.completed"
    assert json.loads(create_route.calls.last.request.content) == {
        "input": "Research hooks",
        "session_id": "session-1",
        "conversation_history": [{"role": "assistant", "content": "Ready"}],
    }


@pytest.mark.asyncio
@respx.mock
async def test_task_polls_after_a_runs_sse_stream_ends_without_a_terminal_event() -> None:
    respx.post("http://hermes/v1/runs").mock(return_value=Response(201, json={"run_id": "run-1"}))
    respx.get("http://hermes/v1/runs/run-1/events").mock(
        return_value=Response(
            200,
            content=b'event: run.progress\ndata: {"run_id":"run-1"}\n\n',
        )
    )
    respx.get("http://hermes/v1/runs/run-1").mock(
        return_value=Response(
            200,
            json={"run_id": "run-1", "status": "completed", "output": "Done"},
        )
    )
    capabilities = HermesCapabilities(
        run_submission=True,
        run_status=True,
        run_events_sse=True,
    )

    async with HermesClient("http://hermes", "secret") as client:
        events = [
            event async for event in client.stream_task(capabilities, "session-1", "Work", [])
        ]

    assert [event.event for event in events] == ["run.progress", "run.completed"]
    assert events[-1].data == {"run_id": "run-1", "output": "Done", "error": None}


@pytest.mark.asyncio
@respx.mock
async def test_task_polls_runs_without_sse_support() -> None:
    respx.post("http://hermes/v1/runs").mock(return_value=Response(201, json={"run_id": "run-1"}))
    respx.get("http://hermes/v1/runs/run-1").mock(
        return_value=Response(
            200,
            json={"run_id": "run-1", "status": "completed", "output": "Done"},
        )
    )
    capabilities = HermesCapabilities(run_submission=True, run_status=True)

    async with HermesClient("http://hermes", "secret") as client:
        events = [
            event async for event in client.stream_task(capabilities, "session-1", "Work", [])
        ]

    assert len(events) == 1
    assert events[0].event == "run.completed"
    assert events[0].data == {"run_id": "run-1", "output": "Done", "error": None}


@pytest.mark.asyncio
@respx.mock
async def test_task_emits_cancelled_when_a_polled_run_is_cancelled() -> None:
    respx.post("http://hermes/v1/runs").mock(return_value=Response(201, json={"run_id": "run-1"}))
    respx.get("http://hermes/v1/runs/run-1").mock(
        return_value=Response(
            200,
            json={"run_id": "run-1", "status": "cancelled"},
        )
    )
    capabilities = HermesCapabilities(run_submission=True, run_status=True)

    async with HermesClient("http://hermes", "secret") as client:
        events = [
            event async for event in client.stream_task(capabilities, "session-1", "Work", [])
        ]

    assert events[0].event == "run.cancelled"
    assert events[0].data == {"run_id": "run-1", "output": None, "error": None}


@pytest.mark.asyncio
async def test_task_rejects_incompatible_capabilities() -> None:
    async with HermesClient("http://hermes", "secret") as client:
        with pytest.raises(RuntimeError, match="neither session streaming nor compatible runs"):
            await anext(client.stream_task(HermesCapabilities(), "session-1", "Work", []))


@pytest.mark.asyncio
@respx.mock
async def test_http_failure_never_discloses_the_bearer_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.get("http://hermes/v1/capabilities").mock(return_value=Response(403, text="denied"))

    async with HermesClient("http://hermes", "secret-token") as client:
        with pytest.raises(httpx.HTTPStatusError) as failure:
            await client.get_capabilities()

    assert "secret-token" not in str(failure.value)
    assert "secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_iter_sse_joins_data_lines_and_dispatches_an_eof_frame() -> None:
    async def lines() -> AsyncIterator[str]:
        yield ": keepalive"
        yield "event: message"
        yield 'data: {"text":"one"'
        yield 'data: ,"next":"two"}'

    events = [event async for event in iter_sse(lines())]

    assert events[0].event == "message"
    assert events[0].data == {"text": "one", "next": "two"}


@pytest.mark.asyncio
async def test_iter_sse_skips_a_malformed_frame_and_keeps_streaming(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def lines() -> AsyncIterator[str]:
        yield "event: malformed"
        yield "data: not-json"
        yield ""
        yield "event: assistant.delta"
        yield 'data: {"text":"Hello"}'
        yield ""

    events = [event async for event in iter_sse(lines())]

    assert [(event.event, event.data) for event in events] == [
        ("assistant.delta", {"text": "Hello"})
    ]
    assert "invalid SSE event" in caplog.text


def test_extract_text_rejects_unknown_content_shapes() -> None:
    with pytest.raises(ValidationError):
        extract_text({"text": "not a message"})
