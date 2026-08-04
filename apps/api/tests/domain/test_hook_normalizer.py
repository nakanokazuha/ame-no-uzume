from typing import cast

import pytest

from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.models import HermesCapabilities
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


def normalizer() -> HermesNormalizer:
    return HermesNormalizer(RoomPolicy([]))


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


def test_subagent_hook_without_an_explicit_child_id_is_ignored() -> None:
    envelope = HookEnvelope.model_validate(
        {
            **start_envelope.model_dump(mode="json"),
            "extra": {"child_role": "researcher"},
        }
    )

    assert normalizer().normalize_hook(envelope, sequence=20) == []


@pytest.mark.asyncio
async def test_accepted_hook_enables_enhanced_telemetry_without_changing_standard_startup() -> None:
    service = WorldService(
        cast("WorldSession", object()),
        cast("WorldClient", object()),
        normalizer(),
        WorldReducer(),
        HermesCapabilities(),
    )

    assert service.snapshot().telemetry_mode == "standard"

    await service.ingest_hook(start_envelope)

    snapshot = service.snapshot()
    worker = next(agent for agent in snapshot.agents if agent.agent_id == "delegated:child-7")
    assert snapshot.telemetry_mode == "enhanced"
    assert worker.display_name == "Researcher"
    assert worker.task_summary == "Compare Hermes event hooks"
