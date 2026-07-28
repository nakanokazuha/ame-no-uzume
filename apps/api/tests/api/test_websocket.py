import asyncio
import json
from collections.abc import AsyncIterator, MutableMapping
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    from fastapi import WebSocket
    from starlette.types import Scope

from yume_api.api.websocket import events
from yume_api.assets.validator import load_and_validate_pack
from yume_api.contracts.events import ConversationMessage, WorldSnapshot
from yume_api.contracts.factories import make_connection_changed
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.models import HermesCapabilities, HermesJob, HermesStreamEvent
from yume_api.main import AppRuntime, create_app
from yume_api.services.world import WorldService

CLIENT_DISCONNECTED_MESSAGE = "client disconnected before accept"
UNREACHABLE_MESSAGE = "unreachable"


class WebSocketSession:
    async def ensure_session(self) -> str:
        return "session-1"

    async def reset_session(self) -> str:
        return "session-2"


class WebSocketHermes:
    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        assert session_id == "session-1"
        return []

    async def list_jobs(self) -> list[HermesJob]:
        return []

    async def stream_task(
        self,
        capabilities: HermesCapabilities,
        session_id: str,
        text: str,
        history: list[ConversationMessage],
    ) -> AsyncIterator[HermesStreamEvent]:
        del capabilities, session_id, text, history
        if False:
            yield HermesStreamEvent(event="unused", data={})

    async def stop_run(self, run_id: str) -> None:
        del run_id

    async def resolve_approval(self, run_id: str, approval_id: str, *, approved: bool) -> None:
        del run_id, approval_id, approved


class RecordingWebSocket:
    def __init__(self, world: WorldService) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(world=world))
        self.accepted = False
        self.sent: list[dict[str, Any]] = []
        self.snapshot_sent = asyncio.Event()

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)
        self.snapshot_sent.set()


class SnapshotRaceWebSocket(RecordingWebSocket):
    def __init__(self, world: WorldService) -> None:
        super().__init__(world)
        self.snapshot_dispatch_started = asyncio.Event()
        self.release_snapshot = asyncio.Event()
        self.live_event_sent = asyncio.Event()

    async def send_json(self, payload: dict[str, Any]) -> None:
        if not self.sent:
            self.snapshot_dispatch_started.set()
            await self.release_snapshot.wait()
        self.sent.append(payload)
        self.snapshot_sent.set()
        if len(self.sent) == 2:
            self.live_event_sent.set()


class FailingAcceptWebSocket(RecordingWebSocket):
    async def accept(self) -> None:
        raise RuntimeError(CLIENT_DISCONNECTED_MESSAGE)


class RegisteredRouteWebSocket:
    def __init__(self) -> None:
        self._received_connect = False
        self.accepted = asyncio.Event()
        self.snapshot_sent = asyncio.Event()
        self.sent: list[dict[str, Any]] = []
        self.live_events_ready = asyncio.Event()

    async def receive(self) -> dict[str, Any]:
        if not self._received_connect:
            self._received_connect = True
            return {"type": "websocket.connect"}
        await asyncio.Event().wait()
        raise AssertionError(UNREACHABLE_MESSAGE)

    async def send(self, message: MutableMapping[str, Any]) -> None:
        if message["type"] == "websocket.accept":
            self.accepted.set()
            return
        assert message["type"] == "websocket.send"
        self.sent.append(json.loads(cast("str", message["text"])))
        if len(self.sent) == 1:
            self.snapshot_sent.set()
        if len(self.sent) == 4:
            self.live_events_ready.set()


class SubscriptionFirstWorld(WorldService):
    def __init__(
        self,
        session: WebSocketSession,
        client: WebSocketHermes,
        normalizer: HermesNormalizer,
        reducer: WorldReducer,
        capabilities: HermesCapabilities,
    ) -> None:
        super().__init__(session, client, normalizer, reducer, capabilities)
        self.snapshot_saw_subscriber = False

    def snapshot(self) -> WorldSnapshot:
        self.snapshot_saw_subscriber = bool(self._subscribers)
        return super().snapshot()


@pytest.mark.asyncio
async def test_websocket_sends_snapshot_before_live_events() -> None:
    capabilities = HermesCapabilities(session_chat_stream=True)
    world = WorldService(
        WebSocketSession(),
        WebSocketHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        capabilities,
    )
    runtime = AppRuntime(
        hermes=WebSocketHermes(),
        world=world,
        capabilities=capabilities,
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
    )
    await world.hydrate()
    assert create_app(runtime=runtime)
    websocket = RecordingWebSocket(world)
    socket_task = asyncio.create_task(events(cast("WebSocket", websocket)))
    await websocket.snapshot_sent.wait()
    socket_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await socket_task

    assert websocket.accepted is True
    assert websocket.sent[0]["type"] == "snapshot.replaced"
    snapshot = cast("dict[str, Any]", websocket.sent[0]["payload"])
    assert snapshot["snapshot"]["agents"][0]["agent_id"] == "yume"


@pytest.mark.asyncio
async def test_websocket_queues_events_published_while_its_snapshot_is_sending() -> None:
    capabilities = HermesCapabilities(session_chat_stream=True)
    world = WorldService(
        WebSocketSession(),
        WebSocketHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        capabilities,
    )
    websocket = SnapshotRaceWebSocket(world)
    socket_task = asyncio.create_task(events(cast("WebSocket", websocket)))
    await websocket.snapshot_dispatch_started.wait()

    await world.publish(make_connection_changed("connected", None, 1))
    websocket.release_snapshot.set()
    await asyncio.wait_for(websocket.live_event_sent.wait(), timeout=0.1)

    socket_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await socket_task

    assert [event["type"] for event in websocket.sent] == [
        "snapshot.replaced",
        "connection.changed",
    ]


@pytest.mark.asyncio
async def test_websocket_registers_before_capturing_its_snapshot() -> None:
    capabilities = HermesCapabilities(session_chat_stream=True)
    world = SubscriptionFirstWorld(
        WebSocketSession(),
        WebSocketHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        capabilities,
    )
    websocket = RecordingWebSocket(world)
    socket_task = asyncio.create_task(events(cast("WebSocket", websocket)))
    await websocket.snapshot_sent.wait()

    socket_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await socket_task

    assert world.snapshot_saw_subscriber is True


@pytest.mark.asyncio
async def test_websocket_removes_a_subscription_when_accept_fails() -> None:
    world = WorldService(
        WebSocketSession(),
        WebSocketHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        HermesCapabilities(session_chat_stream=True),
    )

    with pytest.raises(RuntimeError, match=CLIENT_DISCONNECTED_MESSAGE):
        await events(cast("WebSocket", FailingAcceptWebSocket(world)))

    assert world.subscriber_count() == 0


@pytest.mark.asyncio
async def test_registered_events_route_forwards_a_successful_normalized_task() -> None:
    class TaskHermes(WebSocketHermes):
        async def stream_task(
            self,
            capabilities: HermesCapabilities,
            session_id: str,
            text: str,
            history: list[ConversationMessage],
        ) -> AsyncIterator[HermesStreamEvent]:
            del capabilities, session_id, text, history
            yield HermesStreamEvent(
                event="assistant.completed",
                data={"message_id": "message-1", "output": "Done"},
            )

    capabilities = HermesCapabilities(session_chat_stream=True)
    hermes = TaskHermes()
    world = WorldService(
        WebSocketSession(),
        hermes,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        capabilities,
    )
    runtime = AppRuntime(
        hermes=hermes,
        world=world,
        capabilities=capabilities,
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
    )
    app = create_app(runtime=runtime)
    websocket = RegisteredRouteWebSocket()
    scope = cast(
        "Scope",
        {"type": "websocket", "path": "/api/events", "headers": [], "query_string": b""},
    )

    async with app.router.lifespan_context(app):
        route_task = asyncio.create_task(app(scope, websocket.receive, websocket.send))
        await asyncio.wait_for(websocket.accepted.wait(), timeout=0.1)
        await asyncio.wait_for(websocket.snapshot_sent.wait(), timeout=0.1)
        await world.submit_task("Research hooks")
        await asyncio.wait_for(websocket.live_events_ready.wait(), timeout=0.1)
        route_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await route_task

    assert [event["type"] for event in websocket.sent] == [
        "snapshot.replaced",
        "conversation.user_added",
        "conversation.completed",
        "agent.state_changed",
    ]
