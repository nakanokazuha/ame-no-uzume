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


def test_reducer_ignores_duplicate_and_stale_non_snapshot_events() -> None:
    reducer = WorldReducer()
    reducer.apply(make_agent_state("yume", "working", "work", 2))

    duplicate = reducer.apply(make_connection_changed("connected", None, 2))
    stale = reducer.apply(make_agent_state("yume", "idle", "ceo", 1))

    assert duplicate.sequence == stale.sequence == 2
    assert duplicate.connection == stale.connection == "starting"
    assert duplicate.agents[0].status == stale.agents[0].status == "working"
    assert duplicate.agents[0].room == stale.agents[0].room == "work"


def test_reducer_replaces_snapshot_with_independent_copy() -> None:
    reducer = WorldReducer()
    reducer.apply(make_connection_changed("degraded", None, 100))
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


def test_reducer_blocks_delayed_stream_events_after_a_hook_stop_until_the_hook_restarts() -> None:
    reducer = WorldReducer()
    worker_id = "delegated:child-session-7"
    yume_snapshot = WorldSnapshot(
        sequence=1,
        connection="connected",
        telemetry_mode="enhanced",
        agents=[
            AgentView(
                agent_id="yume",
                kind="yume",
                display_name="Yume",
                status="idle",
                room="ceo",
                evidence="verified",
            )
        ],
    )
    reducer.apply(make_snapshot_event(yume_snapshot))
    reducer.apply(
        make_agent_spawned(
            worker_id,
            "delegated",
            "Researcher",
            "lobby",
            2,
            source="hermes.hook",
        )
    )
    reducer.apply(make_agent_removed(worker_id, 3, source="hermes.hook"))
    reducer.apply(make_snapshot_event(yume_snapshot.model_copy(update={"sequence": 4})))

    reducer.apply(make_agent_spawned(worker_id, "delegated", "Delegated Worker", "lobby", 5))

    assert [agent.agent_id for agent in reducer.snapshot.agents] == ["yume"]

    reopened = reducer.apply(
        make_agent_spawned(
            worker_id,
            "delegated",
            "Researcher",
            "lobby",
            6,
            source="hermes.hook",
        )
    )

    assert [agent.agent_id for agent in reopened.agents] == ["yume", worker_id]


def test_reducer_evicts_the_oldest_hook_terminal_tombstone_at_its_bound() -> None:
    reducer = WorldReducer()
    reducer.apply(
        make_snapshot_event(
            WorldSnapshot(sequence=1, connection="connected", telemetry_mode="enhanced", agents=[])
        )
    )
    for index in range(1_001):
        reducer.apply(
            make_agent_removed(f"delegated:child-{index}", index + 2, source="hermes.hook")
        )

    snapshot = reducer.apply(
        make_agent_spawned("delegated:child-0", "delegated", "Stream worker", "lobby", 1_003)
    )
    snapshot = reducer.apply(
        make_agent_spawned("delegated:child-1", "delegated", "Stream worker", "lobby", 1_004)
    )

    assert [agent.agent_id for agent in snapshot.agents] == ["delegated:child-0"]


def test_reducer_snapshot_reintroduces_a_tombstoned_agent_authoritatively() -> None:
    reducer = WorldReducer()
    worker_id = "delegated:child-session-7"
    reducer.apply(
        make_snapshot_event(
            WorldSnapshot(sequence=1, connection="connected", telemetry_mode="enhanced", agents=[])
        )
    )
    reducer.apply(make_agent_removed(worker_id, 2, source="hermes.hook"))
    reducer.apply(
        make_snapshot_event(
            WorldSnapshot(
                sequence=3,
                connection="connected",
                telemetry_mode="enhanced",
                agents=[
                    AgentView(
                        agent_id=worker_id,
                        kind="delegated",
                        display_name="Researcher",
                        status="working",
                        room="work",
                        evidence="verified",
                    )
                ],
            )
        )
    )

    snapshot = reducer.apply(make_agent_state(worker_id, "completed", "work", 4))

    assert snapshot.agents[0].status == "completed"
