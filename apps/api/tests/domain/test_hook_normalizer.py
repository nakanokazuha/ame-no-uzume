import asyncio
from typing import Literal, cast

import pytest
from pydantic import ValidationError

from yume_api.contracts.events import AgentSpawnedEvent
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.models import HermesCapabilities, HermesStreamEvent
from yume_api.integrations.hook_models import HookEnvelope
from yume_api.services.world import WorldClient, WorldService, WorldSession

start_envelope = HookEnvelope.model_validate(
    {
        "schema_version": 1,
        "event_id": "hook-1",
        "occurred_at": "2026-07-27T00:00:00Z",
        "event": "subagent_start",
        "session_id": "parent-1",
        "extra": {
            "child_subagent_id": "child-7",
            "child_role": "researcher",
            "child_goal": "Compare Hermes event hooks",
        },
    }
)
failed_stop_envelope = HookEnvelope.model_validate(
    {
        **start_envelope.model_dump(mode="json"),
        "event_id": "hook-2",
        "event": "subagent_stop",
        "extra": {"child_subagent_id": "child-7", "child_status": "failed"},
    }
)
native_start_envelope = HookEnvelope.model_validate(
    {
        **start_envelope.model_dump(mode="json"),
        "event_id": "hook-native-start",
        "extra": {
            "child_session_id": "child-session-7",
            "child_subagent_id": "child-7",
            "child_role": "researcher",
            "child_goal": "Compare native Hermes hooks",
        },
    }
)
native_stop_envelope = HookEnvelope.model_validate(
    {
        **native_start_envelope.model_dump(mode="json"),
        "event_id": "hook-native-stop",
        "event": "subagent_stop",
        "extra": {"child_session_id": "child-session-7", "child_status": "completed"},
    }
)
collision_start_envelope = HookEnvelope.model_validate(
    {
        **start_envelope.model_dump(mode="json"),
        "event_id": "hook-collision",
        "extra": {
            "child_subagent_id": "run-1:call-1",
            "child_role": "researcher",
            "child_goal": "Keep this hook worker distinct",
        },
    }
)


def normalizer() -> HermesNormalizer:
    return HermesNormalizer(RoomPolicy([]))


def stream_spawn(sequence: int) -> AgentSpawnedEvent:
    events = normalizer().normalize(
        HermesStreamEvent(
            event="tool.started",
            data={
                "run_id": "run-1",
                "tool_call_id": "call-1",
                "tool_name": "delegate_task",
                "child_subagent_id": "child-7",
            },
        ),
        sequence,
    )
    spawned = events[0]
    assert spawned.type == "agent.spawned"
    return spawned


def stream_fallback_spawn(sequence: int) -> AgentSpawnedEvent:
    events = normalizer().normalize(
        HermesStreamEvent(
            event="tool.started",
            data={
                "run_id": "run-1",
                "tool_call_id": "call-1",
                "tool_name": "delegate_task",
            },
        ),
        sequence,
    )
    spawned = events[0]
    assert spawned.type == "agent.spawned"
    return spawned


def test_subagent_start_uses_verified_role_and_goal() -> None:
    events = normalizer().normalize_hook(start_envelope, sequence=20)
    spawned = events[0]
    assert spawned.type == "agent.spawned"
    assert spawned.agent_id == "delegated:child-7"
    assert spawned.payload.display_name == "Researcher"
    assert spawned.payload.task_summary == "Compare Hermes event hooks"
    assert spawned.evidence == "verified"


def test_subagent_stop_preserves_failure_status() -> None:
    events = normalizer().normalize_hook(failed_stop_envelope, sequence=21)
    assert [event.type for event in events] == ["agent.state_changed", "agent.removed"]
    assert [event.payload.status for event in events if event.type == "agent.state_changed"] == [
        "failed"
    ]


@pytest.mark.asyncio
async def test_native_session_id_removes_the_worker_started_with_both_native_ids() -> None:
    """Use Hermes' child-session key when stop does not carry a subagent ID."""
    service = WorldService(
        cast("WorldSession", object()),
        cast("WorldClient", object()),
        normalizer(),
        WorldReducer(),
        HermesCapabilities(),
    )

    await service.ingest_hook(native_start_envelope)
    assert [agent.agent_id for agent in service.snapshot().agents] == [
        "yume",
        "delegated:child-session-7",
    ]
    await service.ingest_hook(native_stop_envelope)

    assert [agent.agent_id for agent in service.snapshot().agents] == ["yume"]


def test_subagent_stop_requires_an_explicit_status() -> None:
    with pytest.raises(ValidationError, match="subagent stop requires child_status"):
        HookEnvelope.model_validate(
            {
                **failed_stop_envelope.model_dump(mode="json"),
                "extra": {"child_subagent_id": "child-7"},
            }
        )


def test_subagent_hook_without_an_explicit_child_id_is_ignored() -> None:
    envelope = HookEnvelope.model_validate(
        {
            **start_envelope.model_dump(mode="json"),
            "extra": {"child_role": "researcher"},
        }
    )

    assert normalizer().normalize_hook(envelope, sequence=20) == []


@pytest.mark.parametrize("arrival_order", ["hook-first", "stream-first"])
def test_explicit_child_id_keeps_hook_enrichment_for_both_arrival_orders(
    arrival_order: Literal["hook-first", "stream-first"],
) -> None:
    hook_first = arrival_order == "hook-first"
    reducer = WorldReducer()
    hook_spawn = normalizer().normalize_hook(start_envelope, sequence=1 if hook_first else 2)[0]
    stream = stream_spawn(sequence=2 if hook_first else 1)

    for event in (hook_spawn, stream) if hook_first else (stream, hook_spawn):
        reducer.apply(event)

    assert [
        (agent.agent_id, agent.display_name, agent.task_summary)
        for agent in reducer.snapshot.agents
        if agent.agent_id.startswith("delegated:")
    ] == [("delegated:child-7", "Researcher", "Compare Hermes event hooks")]


@pytest.mark.asyncio
@pytest.mark.parametrize("arrival_order", ["hook-first", "stream-first"])
async def test_enhanced_hook_telemetry_replaces_generic_stream_placeholders(
    arrival_order: Literal["hook-first", "stream-first"],
) -> None:
    """Enhanced hooks supersede generic placeholders without correlating their identities."""
    service = WorldService(
        cast("WorldSession", object()),
        cast("WorldClient", object()),
        normalizer(),
        WorldReducer(),
        HermesCapabilities(),
    )
    fallback_spawn = stream_fallback_spawn(sequence=1)
    assert fallback_spawn.agent_id == "stream-delegated:run-1:call-1"

    if arrival_order == "stream-first":
        await service.publish(fallback_spawn)
        await service.ingest_hook(native_start_envelope)
    else:
        await service.ingest_hook(native_start_envelope)
        await service.publish(stream_fallback_spawn(service.snapshot().sequence + 1))

    assert [agent.agent_id for agent in service.snapshot().agents] == [
        "yume",
        "delegated:child-session-7",
    ]


@pytest.mark.asyncio
async def test_accepted_hook_enables_enhanced_telemetry_without_changing_standard_startup() -> None:
    service = WorldService(
        cast("WorldSession", object()),
        cast("WorldClient", object()),
        normalizer(),
        WorldReducer(),
        HermesCapabilities(),
    )

    initial_snapshot, subscription = service.subscribe()
    assert initial_snapshot.telemetry_mode == "standard"
    assert initial_snapshot.sequence == 0

    await service.ingest_hook(start_envelope)

    enhanced_snapshot = await subscription.__anext__()
    spawned = await subscription.__anext__()
    snapshot = service.snapshot()
    worker = next(agent for agent in snapshot.agents if agent.agent_id == "delegated:child-7")
    assert enhanced_snapshot.type == "snapshot.replaced"
    assert enhanced_snapshot.sequence == enhanced_snapshot.payload.snapshot.sequence == 1
    assert spawned.type == "agent.spawned"
    assert spawned.sequence == 2
    assert snapshot.telemetry_mode == "enhanced"
    assert worker.display_name == "Researcher"
    assert worker.task_summary == "Compare Hermes event hooks"


@pytest.mark.asyncio
async def test_hook_owned_worker_suppresses_later_same_identity_stream_events() -> None:
    service = WorldService(
        cast("WorldSession", object()),
        cast("WorldClient", object()),
        normalizer(),
        WorldReducer(),
        HermesCapabilities(),
    )
    _, subscription = service.subscribe()

    await service.ingest_hook(start_envelope)
    await subscription.__anext__()
    await subscription.__anext__()
    await service.publish(stream_spawn(service.snapshot().sequence + 1))

    worker = next(
        agent for agent in service.snapshot().agents if agent.agent_id == "delegated:child-7"
    )
    assert worker.display_name == "Researcher"
    assert worker.task_summary == "Compare Hermes event hooks"
    with pytest.raises(asyncio.QueueEmpty):
        subscription._queue.get_nowait()  # noqa: SLF001
