import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

import yume_api.main as main_module
from yume_api.assets.validator import load_and_validate_pack
from yume_api.contracts.events import ConversationMessage, WorldEvent
from yume_api.contracts.factories import make_connection_changed
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.models import HermesCapabilities, HermesStreamEvent
from yume_api.main import AppRuntime, create_app
from yume_api.services.world import WorldService

STARTUP_FAILURE_MESSAGE = "Hermes is unavailable"
TASK_FAILURE_MESSAGE = "Hermes stream failed"


class FakeSession:
    def __init__(self) -> None:
        self.session_id = "session-1"
        self.reset_count = 0

    async def ensure_session(self) -> str:
        return self.session_id

    async def reset_session(self) -> str:
        self.reset_count += 1
        self.session_id = f"session-{self.reset_count + 1}"
        return self.session_id


class FakeHermes:
    def __init__(self) -> None:
        self.messages = [ConversationMessage(message_id="m1", role="assistant", text="Ready")]
        self.stopped_runs: list[str] = []
        self.approvals: list[tuple[str, str, bool]] = []
        self.task_requests: list[tuple[str, str, list[ConversationMessage]]] = []
        self.task_finished = asyncio.Event()

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        assert session_id
        return self.messages

    async def stream_task(
        self,
        capabilities: HermesCapabilities,
        session_id: str,
        text: str,
        history: list[ConversationMessage],
    ) -> AsyncIterator[HermesStreamEvent]:
        assert capabilities.session_chat_stream
        assert session_id
        assert text
        assert isinstance(history, list)
        self.task_requests.append((session_id, text, history))
        self.task_finished.set()
        if False:
            yield HermesStreamEvent(event="unused", data={})

    async def stop_run(self, run_id: str) -> None:
        self.stopped_runs.append(run_id)

    async def resolve_approval(self, run_id: str, approval_id: str, *, approved: bool) -> None:
        self.approvals.append((run_id, approval_id, approved))


@pytest.fixture
def api_dependencies() -> tuple[AppRuntime, FakeHermes, FakeSession]:
    hermes = FakeHermes()
    session = FakeSession()
    world = WorldService(
        session,
        hermes,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        HermesCapabilities(session_chat_stream=True, run_stop=True, run_approval=True),
    )
    runtime = AppRuntime(
        hermes=hermes,
        world=world,
        capabilities=HermesCapabilities(session_chat_stream=True, run_stop=True, run_approval=True),
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
    )
    return runtime, hermes, session


@asynccontextmanager
async def request_client(runtime: AppRuntime) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(runtime=runtime)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_bootstrap_returns_hydrated_snapshot(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    async with request_client(api_dependencies[0]) as client:
        response = await client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json()["world"]["session_id"] == "session-1"
    assert response.json()["world"]["agents"][0]["agent_id"] == "yume"
    assert response.json()["world"]["conversation"] == [
        {"message_id": "m1", "role": "assistant", "text": "Ready"}
    ]
    assert response.json()["asset_pack"]["id"] == "placeholder"


@pytest.mark.parametrize("text", ["", "   ", "x" * 20_001])
@pytest.mark.asyncio
async def test_task_rejects_blank_or_overlong_input(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession], text: str
) -> None:
    async with request_client(api_dependencies[0]) as client:
        response = await client.post("/api/tasks", json={"text": text})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_task_starts_a_background_stream(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    runtime, hermes, _ = api_dependencies
    async with request_client(runtime) as client:
        response = await client.post("/api/tasks", json={"text": "  Research hooks  "})
        await asyncio.wait_for(hermes.task_finished.wait(), timeout=0.1)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert hermes.task_requests == [
        (
            "session-1",
            "Research hooks",
            [ConversationMessage(message_id="m1", role="assistant", text="Ready")],
        )
    ]


@pytest.mark.asyncio
async def test_task_rejects_a_second_request_while_the_background_stream_is_active(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    class BlockingHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def stream_task(
            self,
            capabilities: HermesCapabilities,
            session_id: str,
            text: str,
            history: list[ConversationMessage],
        ) -> AsyncIterator[HermesStreamEvent]:
            del capabilities, session_id, text, history
            self.started.set()
            await self.release.wait()
            if False:
                yield HermesStreamEvent(event="unused", data={})

    runtime, _, _ = api_dependencies
    hermes = BlockingHermes()
    runtime.hermes = hermes
    runtime.world = WorldService(
        FakeSession(),
        hermes,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        runtime.capabilities,
    )
    async with request_client(runtime) as client:
        first = await client.post("/api/tasks", json={"text": "First"})
        await asyncio.wait_for(hermes.started.wait(), timeout=0.1)
        second = await client.post("/api/tasks", json={"text": "Second"})
        hermes.release.set()

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"] == "a task is already running"


@pytest.mark.asyncio
async def test_task_logs_an_exception_from_its_background_stream(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        async def stream_task(
            self,
            capabilities: HermesCapabilities,
            session_id: str,
            text: str,
            history: list[ConversationMessage],
        ) -> AsyncIterator[HermesStreamEvent]:
            del capabilities, session_id, text, history
            self.started.set()
            raise RuntimeError(TASK_FAILURE_MESSAGE)
            if False:
                yield HermesStreamEvent(event="unused", data={})

    runtime, _, _ = api_dependencies
    hermes = FailingHermes()
    runtime.hermes = hermes
    runtime.world = WorldService(
        FakeSession(),
        hermes,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        runtime.capabilities,
    )
    caplog.set_level(logging.ERROR, logger="yume_api.api.routes")
    async with request_client(runtime) as client:
        response = await client.post("/api/tasks", json={"text": "Research hooks"})
        await asyncio.wait_for(hermes.started.wait(), timeout=0.1)
        await asyncio.sleep(0)

    assert response.status_code == 202
    assert "dashboard task stream failed" in caplog.text
    assert TASK_FAILURE_MESSAGE in caplog.text


@pytest.mark.asyncio
async def test_reset_replaces_session_and_clears_transcript(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    async with request_client(api_dependencies[0]) as client:
        response = await client.post("/api/session/reset")
        bootstrap = await client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json() == {"session_id": "session-2"}
    assert bootstrap.json()["world"]["conversation"] == []
    assert api_dependencies[2].reset_count == 1


@pytest.mark.asyncio
async def test_reset_rejects_while_a_task_stream_is_active(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    class BlockingHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def stream_task(
            self,
            capabilities: HermesCapabilities,
            session_id: str,
            text: str,
            history: list[ConversationMessage],
        ) -> AsyncIterator[HermesStreamEvent]:
            del capabilities, session_id, text, history
            self.started.set()
            await self.release.wait()
            if False:
                yield HermesStreamEvent(event="unused", data={})

    runtime, _, session = api_dependencies
    hermes = BlockingHermes()
    world = WorldService(
        session,
        hermes,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        runtime.capabilities,
    )
    runtime.hermes = hermes
    runtime.world = world
    async with request_client(runtime) as client:
        accepted = await client.post("/api/tasks", json={"text": "Research hooks"})
        await asyncio.wait_for(hermes.started.wait(), timeout=0.1)
        reset = await client.post("/api/session/reset")
        hermes.release.set()

    assert accepted.status_code == 202
    assert reset.status_code == 409
    assert session.reset_count == 0
    assert world.snapshot().session_id == "session-1"


@pytest.mark.asyncio
async def test_reset_cannot_precede_an_accepted_task_before_its_stream_starts(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    class DelayedTaskWorld(WorldService):
        def __init__(
            self,
            session: FakeSession,
            client: FakeHermes,
            normalizer: HermesNormalizer,
            reducer: WorldReducer,
            capabilities: HermesCapabilities,
        ) -> None:
            super().__init__(session, client, normalizer, reducer, capabilities)
            self.stream_scheduled = asyncio.Event()
            self.release_stream = asyncio.Event()

        async def run_reserved_task(self, text: str) -> str:
            self.stream_scheduled.set()
            await self.release_stream.wait()
            return await super().run_reserved_task(text)

    runtime, hermes, session = api_dependencies
    world = DelayedTaskWorld(
        session,
        hermes,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        runtime.capabilities,
    )
    runtime.world = world
    async with request_client(runtime) as client:
        accepted = await client.post("/api/tasks", json={"text": "Research hooks"})
        await asyncio.wait_for(world.stream_scheduled.wait(), timeout=0.1)
        reset = await client.post("/api/session/reset")
        world.release_stream.set()

    assert accepted.status_code == 202
    assert reset.status_code == 409
    assert session.reset_count == 0


@pytest.mark.asyncio
async def test_stop_and_approval_call_only_supported_hermes_operations(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    async with request_client(api_dependencies[0]) as client:
        stop_response = await client.post("/api/runs/run-1/stop")
        approval_response = await client.post(
            "/api/runs/run-1/approval", json={"approval_id": "approval-1", "approved": True}
        )

    assert stop_response.status_code == 200
    assert approval_response.status_code == 200
    assert api_dependencies[1].stopped_runs == ["run-1"]
    assert api_dependencies[1].approvals == [("run-1", "approval-1", True)]


@pytest.mark.asyncio
async def test_stop_and_approval_return_not_implemented_when_unavailable(
    api_dependencies: tuple[AppRuntime, FakeHermes, FakeSession],
) -> None:
    runtime, hermes, _ = api_dependencies
    runtime.capabilities = HermesCapabilities(session_chat_stream=True)
    async with request_client(runtime) as client:
        stop_response = await client.post("/api/runs/run-1/stop")
        approval_response = await client.post(
            "/api/runs/run-1/approval", json={"approval_id": "approval-1", "approved": False}
        )

    assert stop_response.status_code == approval_response.status_code == 501
    assert hermes.stopped_runs == []
    assert hermes.approvals == []


@pytest.mark.asyncio
async def test_lifespan_cancels_active_tasks_before_closing_hermes() -> None:
    class CancellableHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.stream_cancelled = asyncio.Event()
            self.closed = False

        async def stream_task(
            self,
            capabilities: HermesCapabilities,
            session_id: str,
            text: str,
            history: list[ConversationMessage],
        ) -> AsyncIterator[HermesStreamEvent]:
            del capabilities, session_id, text, history
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.stream_cancelled.set()
            if False:
                yield HermesStreamEvent(event="unused", data={})

        async def aclose(self) -> None:
            assert self.stream_cancelled.is_set()
            self.closed = True

    hermes = CancellableHermes()
    capabilities = HermesCapabilities(session_chat_stream=True)
    runtime = AppRuntime(
        hermes=hermes,
        world=WorldService(
            FakeSession(),
            hermes,
            HermesNormalizer(RoomPolicy([])),
            WorldReducer(),
            capabilities,
        ),
        capabilities=capabilities,
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
        close_hermes=True,
    )
    app = create_app(runtime=runtime)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/tasks", json={"text": "Research hooks"})
            await asyncio.wait_for(hermes.started.wait(), timeout=0.1)

    assert response.status_code == 202
    assert hermes.stream_cancelled.is_set()
    assert hermes.closed is True


@pytest.mark.asyncio
async def test_production_lifespan_discovers_capabilities_and_closes_owned_hermes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProductionHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.discovered = False
            self.closed = False

        async def get_capabilities(self) -> HermesCapabilities:
            self.discovered = True
            return HermesCapabilities(session_chat_stream=True, run_stop=True)

        async def aclose(self) -> None:
            self.closed = True

    hermes = ProductionHermes()
    initial_capabilities = HermesCapabilities()
    runtime = AppRuntime(
        hermes=hermes,
        world=WorldService(
            FakeSession(),
            hermes,
            HermesNormalizer(RoomPolicy([])),
            WorldReducer(),
            initial_capabilities,
        ),
        capabilities=initial_capabilities,
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
        close_hermes=True,
    )
    monkeypatch.setattr(main_module, "_build_runtime", lambda: runtime)
    app = create_app()

    async with app.router.lifespan_context(app):
        assert app.state.capabilities == HermesCapabilities(session_chat_stream=True, run_stop=True)
        await runtime.world.submit_task("Verify discovered capabilities")

    assert hermes.discovered is True
    assert hermes.closed is True


@pytest.mark.asyncio
async def test_production_lifespan_closes_owned_hermes_after_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.closed = False

        async def get_capabilities(self) -> HermesCapabilities:
            return HermesCapabilities(session_chat_stream=True)

        async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
            del session_id
            raise RuntimeError(STARTUP_FAILURE_MESSAGE)

        async def aclose(self) -> None:
            self.closed = True

    hermes = FailingHermes()
    initial_capabilities = HermesCapabilities()
    runtime = AppRuntime(
        hermes=hermes,
        world=WorldService(
            FakeSession(),
            hermes,
            HermesNormalizer(RoomPolicy([])),
            WorldReducer(),
            initial_capabilities,
        ),
        capabilities=initial_capabilities,
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
        close_hermes=True,
    )
    monkeypatch.setattr(main_module, "_build_runtime", lambda: runtime)
    app = create_app()

    with pytest.raises(RuntimeError, match=STARTUP_FAILURE_MESSAGE):
        async with app.router.lifespan_context(app):
            pass

    assert hermes.closed is True


@pytest.mark.asyncio
async def test_world_service_resets_normalizer_before_and_after_a_task_stream() -> None:
    class RecordingNormalizer:
        def __init__(self) -> None:
            self.reset_count = 0

        def reset(self) -> None:
            self.reset_count += 1

        def normalize(self, event: HermesStreamEvent, sequence: int) -> list[WorldEvent]:
            del event, sequence
            return []

    normalizer = RecordingNormalizer()
    world = WorldService(
        FakeSession(),
        FakeHermes(),
        normalizer,
        WorldReducer(),
        HermesCapabilities(session_chat_stream=True),
    )

    session_id = await world.submit_task("Research the roadmap")

    assert session_id == "session-1"
    assert normalizer.reset_count == 2


@pytest.mark.asyncio
async def test_world_service_rejects_a_second_concurrent_task() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingHermes(FakeHermes):
        async def stream_task(
            self,
            capabilities: HermesCapabilities,
            session_id: str,
            text: str,
            history: list[ConversationMessage],
        ) -> AsyncIterator[HermesStreamEvent]:
            del capabilities, session_id, text, history
            started.set()
            await release.wait()
            if False:
                yield HermesStreamEvent(event="unused", data={})

    world = WorldService(
        FakeSession(),
        BlockingHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        HermesCapabilities(session_chat_stream=True),
    )
    running_task = asyncio.create_task(world.submit_task("First task"))
    await started.wait()

    with pytest.raises(RuntimeError, match="already running"):
        await world.submit_task("Second task")

    release.set()
    await running_task


@pytest.mark.asyncio
async def test_world_service_replaces_a_missing_persisted_session_once() -> None:
    class MissingSessionHermes(FakeHermes):
        async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
            request = httpx.Request("GET", f"http://hermes/api/sessions/{session_id}/messages")
            response = httpx.Response(404, request=request)
            message = "missing"
            raise httpx.HTTPStatusError(message, request=request, response=response)

    session = FakeSession()
    world = WorldService(
        session,
        MissingSessionHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        HermesCapabilities(session_chat_stream=True),
    )

    await world.hydrate()

    assert session.reset_count == 1
    assert world.snapshot().session_id == "session-2"
    assert world.snapshot().conversation == []


@pytest.mark.asyncio
async def test_subscriber_queue_evicts_the_oldest_event_when_full() -> None:
    world = WorldService(
        FakeSession(),
        FakeHermes(),
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        HermesCapabilities(session_chat_stream=True),
        subscriber_queue_size=2,
    )
    _, subscription = world.subscribe()
    first_event = asyncio.ensure_future(anext(subscription))
    await asyncio.sleep(0)
    await world.publish(make_connection_changed("connected", None, 1))
    assert (await first_event).sequence == 1
    await world.publish(make_connection_changed("degraded", None, 2))
    await world.publish(make_connection_changed("disconnected", None, 3))
    await world.publish(make_connection_changed("starting", None, 4))

    assert (await anext(subscription)).sequence == 3
    assert (await anext(subscription)).sequence == 4
    await subscription.aclose()
