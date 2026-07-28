import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from yume_api.contracts.events import (
    AgentRemovedEvent,
    AgentSpawnedEvent,
    AgentStateChangedEvent,
    AgentTaskChangedEvent,
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    ConnectionChangedEvent,
    ConversationCompletedEvent,
    ConversationDeltaEvent,
    ConversationUserAddedEvent,
    RunFinishedEvent,
    SnapshotReplacedEvent,
    WorldEvent,
)


def _event(
    event_type: str,
    payload: dict[str, Any],
    *,
    agent_id: str | None = None,
    schema_version: int = 1,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": schema_version,
        "event_id": "evt-1",
        "sequence": 1,
        "occurred_at": "2026-07-27T00:00:00Z",
        "source": "hermes.session_stream",
        "evidence": "verified",
        "type": event_type,
        "payload": payload,
    }
    if agent_id is not None:
        event["agent_id"] = agent_id
    return event


EVENT_FIXTURES: list[tuple[dict[str, Any], type[object]]] = [
    (
        _event(
            "agent.spawned",
            {
                "kind": "delegated",
                "display_name": "Delegated Worker",
                "status": "entering",
                "room": "lobby",
            },
            agent_id="delegated:run-1:call-1",
        ),
        AgentSpawnedEvent,
    ),
    (
        _event(
            "agent.state_changed",
            {"status": "working", "room": "work"},
            agent_id="delegated:run-1:call-1",
        ),
        AgentStateChangedEvent,
    ),
    (
        _event(
            "agent.task_changed",
            {"task_summary": "Review dashboard event coverage"},
            agent_id="delegated:run-1:call-1",
        ),
        AgentTaskChangedEvent,
    ),
    (
        _event(
            "agent.removed",
            {},
            agent_id="delegated:run-1:call-1",
        ),
        AgentRemovedEvent,
    ),
    (
        _event(
            "connection.changed",
            {"status": "connected", "reason": "stream restored"},
        ),
        ConnectionChangedEvent,
    ),
    (
        _event(
            "snapshot.replaced",
            {
                "snapshot": {
                    "sequence": 1,
                    "connection": "connected",
                    "agents": [],
                }
            },
        ),
        SnapshotReplacedEvent,
    ),
    (
        _event(
            "conversation.user_added",
            {"message_id": "msg-1", "text": "What is running?"},
        ),
        ConversationUserAddedEvent,
    ),
    (
        _event(
            "conversation.delta",
            {"message_id": "msg-2", "text": "Investigating"},
        ),
        ConversationDeltaEvent,
    ),
    (
        _event(
            "conversation.completed",
            {"message_id": "msg-2", "text": "Investigation complete"},
        ),
        ConversationCompletedEvent,
    ),
    (
        _event(
            "approval.requested",
            {
                "run_id": "run-1",
                "approval_id": "approval-1",
                "prompt": "Allow deployment?",
            },
            agent_id="delegated:run-1:call-1",
        ),
        ApprovalRequestedEvent,
    ),
    (
        _event(
            "approval.resolved",
            {"decision": "approved"},
            agent_id="delegated:run-1:call-1",
        ),
        ApprovalResolvedEvent,
    ),
    (
        _event(
            "run.finished",
            {"run_id": "run-1", "outcome": "completed"},
        ),
        RunFinishedEvent,
    ),
]


@pytest.mark.parametrize(
    ("event_data", "expected_type"),
    EVENT_FIXTURES,
    ids=[event_data["type"] for event_data, _ in EVENT_FIXTURES],
)
def test_every_world_event_variant_is_discriminated(
    event_data: dict[str, Any], expected_type: type[object]
) -> None:
    event = TypeAdapter(WorldEvent).validate_python(event_data)

    assert isinstance(event, expected_type)


def test_agent_task_changed_event_has_a_typed_summary_payload() -> None:
    event = TypeAdapter(WorldEvent).validate_python(EVENT_FIXTURES[2][0])

    assert isinstance(event, AgentTaskChangedEvent)
    assert event.payload.task_summary == "Review dashboard event coverage"


@pytest.mark.parametrize(
    "event_data",
    [
        _event("agent.unknown", {}),
        _event(
            "agent.spawned",
            {
                "kind": "delegated",
                "display_name": "Delegated Worker",
                "status": "entering",
                "room": "lobby",
            },
            agent_id="delegated:run-1:call-1",
            schema_version=2,
        ),
    ],
    ids=["unknown-discriminator", "unsupported-schema-version"],
)
def test_world_event_rejects_unknown_discriminators_and_schema_versions(
    event_data: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(WorldEvent).validate_python(event_data)


def test_generated_schema_matches_current_world_event_model() -> None:
    schema_path = (
        Path(__file__).resolve().parents[4] / "packages/contracts/schemas/world-event.schema.json"
    )

    assert (
        json.loads(schema_path.read_text(encoding="utf-8")) == TypeAdapter(WorldEvent).json_schema()
    )
