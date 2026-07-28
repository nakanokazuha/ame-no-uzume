from yume_api.contracts.events import AgentView, ConversationMessage, WorldSnapshot
from yume_api.contracts.factories import (
    make_agent_removed,
    make_agent_spawned,
    make_agent_state,
    make_connection_changed,
    make_conversation_completed,
    make_snapshot_event,
    make_user_message,
)
from yume_api.domain.reducer import WorldReducer


def test_reducer_starts_with_persistent_yume() -> None:
    reducer = WorldReducer()

    assert reducer.snapshot.connection == "starting"
    assert [(agent.agent_id, agent.kind, agent.room) for agent in reducer.snapshot.agents] == [
        ("yume", "yume", "ceo")
    ]


def test_reducer_adds_updates_and_removes_ephemeral_worker() -> None:
    reducer = WorldReducer()
    reducer.apply(make_agent_spawned("delegated:run-1:call-1", "delegated", "Worker", "lobby", 1))
    changed = reducer.apply(
        make_agent_state("delegated:run-1:call-1", "working", "work", 2, task_summary="Task")
    )
    removed = reducer.apply(make_agent_removed("delegated:run-1:call-1", 3))

    assert changed.agents[1].status == "working"
    assert changed.agents[1].room == "work"
    assert changed.agents[1].task_summary == "Task"
    assert [agent.agent_id for agent in removed.agents] == ["yume"]


def test_reducer_keeps_yume_when_remove_event_targets_it() -> None:
    reducer = WorldReducer()

    snapshot = reducer.apply(make_agent_removed("yume", 1))

    assert [agent.agent_id for agent in snapshot.agents] == ["yume"]


def test_reducer_records_connection_and_completed_conversation() -> None:
    reducer = WorldReducer()
    reducer.apply(make_connection_changed("connected", "stream restored", 1))
    reducer.apply(make_user_message("What is running?", 2))
    snapshot = reducer.apply(
        make_conversation_completed({"run_id": "run-1", "output": "All clear"}, 3)
    )

    assert snapshot.connection == "connected"
    assert [(message.role, message.text) for message in snapshot.conversation] == [
        ("user", "What is running?"),
        ("assistant", "All clear"),
    ]


def test_reducer_returns_deep_copies_that_cannot_mutate_authoritative_state() -> None:
    reducer = WorldReducer()
    returned = reducer.apply(make_connection_changed("connected", None, 1))
    returned.agents[0].display_name = "Mutated"
    returned.conversation.append(
        ConversationMessage(message_id="fake", role="assistant", text="Injected")
    )

    next_snapshot = reducer.apply(make_connection_changed("degraded", None, 2))

    assert next_snapshot.agents[0].display_name == "Yume"
    assert next_snapshot.conversation == []
    assert next_snapshot.connection == "degraded"


def test_reducer_replaces_snapshot_with_independent_copy() -> None:
    reducer = WorldReducer()
    replacement = WorldSnapshot(
        sequence=50,
        connection="connected",
        agents=[
            AgentView(
                agent_id="yume",
                kind="yume",
                display_name="Yume",
                status="thinking",
                room="ceo",
                evidence="verified",
            )
        ],
    )

    returned = reducer.apply(make_snapshot_event(replacement))
    returned.agents[0].status = "failed"
    replacement.agents[0].status = "idle"

    snapshot = reducer.apply(make_connection_changed("degraded", None, 51))

    assert snapshot.sequence == 51
    assert snapshot.agents[0].status == "thinking"
