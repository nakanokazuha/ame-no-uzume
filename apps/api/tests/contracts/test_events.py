from pydantic import TypeAdapter
from yume_api.contracts.events import AgentSpawnedEvent, WorldEvent


def test_agent_spawned_event_is_discriminated() -> None:
    event = TypeAdapter(WorldEvent).validate_python(
        {
            "schema_version": 1,
            "event_id": "evt-1",
            "sequence": 1,
            "occurred_at": "2026-07-27T00:00:00Z",
            "source": "hermes.session_stream",
            "evidence": "verified",
            "type": "agent.spawned",
            "agent_id": "delegated:run-1:call-1",
            "payload": {
                "kind": "delegated",
                "display_name": "Delegated Worker",
                "status": "entering",
                "room": "lobby",
            },
        }
    )

    assert isinstance(event, AgentSpawnedEvent)
    assert event.payload.room == "lobby"
