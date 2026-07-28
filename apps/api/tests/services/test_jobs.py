import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response
from pydantic import TypeAdapter, ValidationError

import yume_api.services.world as world_module
from yume_api.assets.validator import load_and_validate_pack
from yume_api.contracts.events import ConversationMessage
from yume_api.contracts.factories import make_agent_spawned
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.client import HermesClient
from yume_api.hermes.models import HermesCapabilities, HermesJob, HermesStreamEvent
from yume_api.main import AppRuntime, create_app
from yume_api.services.jobs import JobSynchronizer
from yume_api.services.world import WorldService

JOB_FAILURE_MESSAGE = "Hermes is unavailable"


def test_job_becomes_persistent_automation_worker() -> None:
    events = JobSynchronizer().reconcile(
        [
            HermesJob(
                id="daily-memory",
                name="Daily memory",
                next_run_at="2026-07-28T00:00:00Z",
            )
        ],
        WorldReducer().snapshot,
        sequence=1,
    )

    assert events[0].type == "agent.spawned"
    assert events[0].agent_id == "scheduled:daily-memory"
    assert events[0].payload.kind == "scheduled"
    assert events[0].payload.room == "automation"
    assert events[0].source == "hermes.jobs"


def test_reconcile_updates_and_removes_scheduled_workers_after_a_successful_response() -> None:
    reducer = WorldReducer()
    reducer.apply(
        make_agent_spawned(
            "scheduled:daily-memory",
            "scheduled",
            "Daily memory",
            "automation",
            1,
            status="idle",
            next_run_at=datetime(2026, 7, 27, tzinfo=UTC),
        )
    )
    synchronizer = JobSynchronizer()

    update_events = synchronizer.reconcile(
        [
            HermesJob(
                id="daily-memory",
                name="Daily memory",
                next_run_at="2026-07-28T00:00:00Z",
            )
        ],
        reducer.snapshot,
        sequence=2,
    )
    remove_events = synchronizer.reconcile([], reducer.snapshot, sequence=3)

    assert len(update_events) == 1
    assert update_events[0].type == "agent.state_changed"
    assert update_events[0].sequence == 2
    assert update_events[0].agent_id == "scheduled:daily-memory"
    assert update_events[0].payload.next_run_at == datetime(2026, 7, 28, tzinfo=UTC)
    assert update_events[0].source == "hermes.jobs"
    assert len(remove_events) == 1
    assert remove_events[0].type == "agent.removed"
    assert remove_events[0].sequence == 3
    assert remove_events[0].agent_id == "scheduled:daily-memory"
    assert remove_events[0].source == "hermes.jobs"


@pytest.mark.asyncio
@respx.mock
async def test_list_jobs_validates_the_hermes_jobs_response() -> None:
    route = respx.get("http://hermes/api/jobs").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": "daily-memory",
                    "name": "Daily memory",
                    "next_run_at": "2026-07-28T00:00:00Z",
                }
            ],
        )
    )

    async with HermesClient("http://hermes", "secret") as client:
        jobs = await client.list_jobs()

    assert jobs == [
        HermesJob(
            id="daily-memory",
            name="Daily memory",
            next_run_at="2026-07-28T00:00:00Z",
        )
    ]
    assert route.called


class FailingJobClient:
    def __init__(self) -> None:
        self.failed = asyncio.Event()

    async def list_jobs(self) -> list[HermesJob]:
        self.failed.set()
        raise httpx.ConnectError(JOB_FAILURE_MESSAGE)

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        del session_id
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


class EmptySession:
    async def ensure_session(self) -> str:
        return "session-1"

    async def reset_session(self) -> str:
        return "session-2"


class RecoveringJobClient:
    def __init__(self, failed_poll: Callable[[], BaseException]) -> None:
        self._failed_poll = failed_poll
        self._poll_count = 0
        self.recovered = asyncio.Event()

    async def list_jobs(self) -> list[HermesJob]:
        self._poll_count += 1
        if self._poll_count == 1:
            raise self._failed_poll()
        self.recovered.set()
        return [
            HermesJob(id="daily-memory", name="Daily memory"),
            HermesJob(id="weekly-review", name="Weekly review"),
        ]

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        del session_id
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


def malformed_jobs_response() -> ValidationError:
    """Return the validation error a partial jobs response produces."""
    with pytest.raises(ValidationError) as failure:
        TypeAdapter(list[HermesJob]).validate_python([{"id": "weekly-review"}])
    return failure.value


@pytest.mark.parametrize(
    "failed_poll",
    [
        pytest.param(malformed_jobs_response, id="partial-response"),
        pytest.param(lambda: httpx.ReadError(JOB_FAILURE_MESSAGE), id="request-error"),
    ],
)
@pytest.mark.asyncio
async def test_job_poller_recovers_after_an_unsuccessful_poll_without_removing_workers(
    monkeypatch: pytest.MonkeyPatch, failed_poll: Callable[[], BaseException]
) -> None:
    reducer = WorldReducer()
    reducer.apply(
        make_agent_spawned(
            "scheduled:daily-memory",
            "scheduled",
            "Daily memory",
            "automation",
            1,
            status="idle",
        )
    )
    client = RecoveringJobClient(failed_poll)
    world = WorldService(
        EmptySession(),
        client,
        HermesNormalizer(RoomPolicy([])),
        reducer,
        HermesCapabilities(),
    )

    async def wait_after_recovery(seconds: float) -> None:
        del seconds
        if client.recovered.is_set():
            await asyncio.Event().wait()

    monkeypatch.setattr(world_module.asyncio, "sleep", wait_after_recovery)
    poll_task = asyncio.create_task(world.poll_jobs())

    await asyncio.wait_for(client.recovered.wait(), timeout=0.1)

    snapshot = world.snapshot()
    assert not poll_task.done()
    assert snapshot.connection == "degraded"
    assert [agent.agent_id for agent in snapshot.agents] == [
        "yume",
        "scheduled:daily-memory",
        "scheduled:weekly-review",
    ]
    poll_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await poll_task


@pytest.mark.asyncio
async def test_failed_job_poll_keeps_existing_workers() -> None:
    reducer = WorldReducer()
    reducer.apply(
        make_agent_spawned(
            "scheduled:daily-memory",
            "scheduled",
            "Daily memory",
            "automation",
            1,
            status="idle",
        )
    )
    client = FailingJobClient()
    world = WorldService(
        EmptySession(),
        client,
        HermesNormalizer(RoomPolicy([])),
        reducer,
        HermesCapabilities(),
    )
    poll_task = asyncio.create_task(world.poll_jobs())

    await asyncio.wait_for(client.failed.wait(), timeout=0.1)
    poll_task.cancel()
    await asyncio.gather(poll_task, return_exceptions=True)

    snapshot = world.snapshot()
    assert snapshot.connection == "degraded"
    assert [agent.agent_id for agent in snapshot.agents] == ["yume", "scheduled:daily-memory"]


class OneJobClient:
    def __init__(self) -> None:
        self.polled = asyncio.Event()

    async def list_jobs(self) -> list[HermesJob]:
        self.polled.set()
        return [HermesJob(id="daily-memory", name="Daily memory")]

    async def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        del session_id
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


@pytest.mark.asyncio
async def test_lifespan_starts_the_scheduled_job_poller() -> None:
    client = OneJobClient()
    world = WorldService(
        EmptySession(),
        client,
        HermesNormalizer(RoomPolicy([])),
        WorldReducer(),
        HermesCapabilities(),
    )
    runtime = AppRuntime(
        hermes=client,
        world=world,
        capabilities=HermesCapabilities(),
        asset_pack=load_and_validate_pack(Path("asset-packs/placeholder")),
    )
    app = create_app(runtime=runtime)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(client.polled.wait(), timeout=0.1)
        assert [agent.agent_id for agent in world.snapshot().agents] == [
            "yume",
            "scheduled:daily-memory",
        ]

    assert all(task.cancelled() for task in app.state.background_tasks)
