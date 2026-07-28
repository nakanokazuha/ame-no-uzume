from typing import Any, cast

import pytest
from pydantic import TypeAdapter

from yume_api.contracts.events import WorldEvent
from yume_api.contracts.factories import (
    make_agent_removed,
    make_agent_spawned,
    make_agent_state,
    make_approval_requested,
    make_connection_changed,
    make_conversation_completed,
    make_conversation_delta,
    make_run_finished,
    make_snapshot_event,
    make_user_message,
)
from yume_api.domain.normalizer import HermesNormalizer
from yume_api.domain.reducer import WorldReducer
from yume_api.domain.room_policy import RoomPolicy
from yume_api.hermes.models import HermesStreamEvent


def _normalizer() -> HermesNormalizer:
    return HermesNormalizer(RoomPolicy([]))


def _event(event: str, data: dict[str, Any]) -> HermesStreamEvent:
    return HermesStreamEvent(event=event, data=data)


def test_delegate_tool_spawns_generic_verified_worker() -> None:
    events = _normalizer().normalize(
        _event(
            "tool.started",
            {"run_id": "run-1", "tool_call_id": "call-2", "tool_name": "delegate_task"},
        ),
        sequence=5,
    )

    spawned = events[0]
    assert spawned.type == "agent.spawned"
    assert spawned.agent_id == "delegated:run-1:call-2"
    assert spawned.evidence == "verified"
    assert spawned.payload.display_name == "Delegated Worker"
    assert spawned.payload.room == "lobby"
    assert spawned.payload.task_summary is None


def test_normalize_maps_unknown_tool_to_verified_generic_work() -> None:
    events = _normalizer().normalize(
        _event("tool.started", {"tool_name": "brand_new_tool", "ignored": "not in payload"}),
        sequence=3,
    )

    assert len(events) == 1
    assert events[0].type == "agent.state_changed"
    assert events[0].agent_id == "yume"
    assert events[0].evidence == "verified"
    assert events[0].payload.status == "working"
    assert events[0].payload.room == "work"
    assert events[0].payload.task_summary is None


def test_normalize_ignores_unknown_events_and_incomplete_delegation() -> None:
    assert _normalizer().normalize(_event("run.progress", {"step": "hidden"}), 1) == []
    assert (
        _normalizer().normalize(
            _event("tool.started", {"tool_name": "delegate_task", "run_id": "run-1"}), 2
        )
        == []
    )


def test_normalize_completed_delegation_emits_completion_then_removal() -> None:
    events = _normalizer().normalize(
        _event("tool.completed", {"run_id": "run-1", "tool_call_id": "call-2"}), 7
    )

    assert [(event.type, event.sequence) for event in events] == [
        ("agent.state_changed", 7),
        ("agent.removed", 8),
    ]
    completed, removed = events
    assert completed.type == "agent.state_changed"
    assert removed.type == "agent.removed"
    assert completed.agent_id == removed.agent_id == "delegated:run-1:call-2"
    assert completed.payload.status == "completed"


def test_native_session_text_is_completed_with_the_server_message_id() -> None:
    normalizer = _normalizer()

    first_delta = normalizer.normalize(_event("assistant.delta", {"text": "Hel"}), 1)
    second_delta = normalizer.normalize(_event("assistant.delta", {"text": "lo"}), 2)
    completed = normalizer.normalize(
        _event("assistant.completed", {"message_id": "msg-1", "output": None}), 3
    )

    assert first_delta == second_delta == []
    assert [(event.type, event.sequence) for event in completed] == [
        ("conversation.completed", 3),
        ("agent.state_changed", 4),
    ]
    message, yume_state = completed
    assert message.type == "conversation.completed"
    assert message.payload.message_id == "msg-1"
    assert message.payload.text == "Hello"
    assert yume_state.type == "agent.state_changed"
    assert yume_state.agent_id == "yume"
    assert yume_state.payload.status == "idle"


def test_normalize_approval_marks_relevant_agent_then_requests_approval() -> None:
    events = _normalizer().normalize(
        _event(
            "approval.requested",
            {
                "run_id": "run-1",
                "approval_id": "approval-1",
                "agent_id": "scheduled:daily",
                "prompt": "Allow deployment?",
            },
        ),
        10,
    )

    assert [(event.type, event.sequence) for event in events] == [
        ("agent.state_changed", 10),
        ("approval.requested", 11),
    ]
    state_changed, requested = events
    assert state_changed.type == "agent.state_changed"
    assert requested.type == "approval.requested"
    assert state_changed.agent_id == requested.agent_id == "scheduled:daily"
    assert state_changed.payload.status == "waiting_approval"
    assert requested.payload.prompt == "Allow deployment?"


def test_normalize_terminal_runs_preserves_cancelled_outcome_and_yume() -> None:
    cancelled = _normalizer().normalize(_event("run.cancelled", {"run_id": "run-1"}), 20)
    completed = _normalizer().normalize(
        _event("run.completed", {"run_id": "run-2", "output": "Done", "message_id": "msg-2"}),
        30,
    )

    assert [(event.type, event.sequence) for event in cancelled] == [
        ("run.finished", 20),
        ("agent.state_changed", 21),
    ]
    finished, yume_state = cancelled
    assert finished.type == "run.finished"
    assert yume_state.type == "agent.state_changed"
    assert finished.payload.outcome == "cancelled"
    assert yume_state.agent_id == "yume"
    assert yume_state.payload.status == "idle"
    assert [(event.type, event.sequence) for event in completed] == [
        ("conversation.completed", 30),
        ("run.finished", 31),
        ("agent.state_changed", 32),
    ]


@pytest.mark.parametrize(
    ("event_name", "outcome"),
    [("run.failed", "failed"), ("run.cancelled", "cancelled")],
)
def test_terminal_delegated_runs_emit_a_terminal_state_before_removal(
    event_name: str, outcome: str
) -> None:
    events = _normalizer().normalize(
        _event(event_name, {"run_id": "run-1", "tool_call_id": "call-2"}), 10
    )

    assert [(event.type, event.sequence) for event in events] == [
        ("run.finished", 10),
        ("agent.state_changed", 11),
        ("agent.removed", 12),
        ("agent.state_changed", 13),
    ]
    finished, worker_state, removed, yume_state = events
    assert finished.type == "run.finished"
    assert finished.payload.outcome == outcome
    assert worker_state.type == "agent.state_changed"
    assert worker_state.agent_id == "delegated:run-1:call-2"
    assert worker_state.payload.status == "failed"
    assert removed.type == "agent.removed"
    assert removed.agent_id == worker_state.agent_id
    assert yume_state.type == "agent.state_changed"
    assert yume_state.agent_id == "yume"


@pytest.mark.parametrize(
    "event",
    [
        make_agent_state("yume", "idle", "ceo", 1),
        make_agent_removed("delegated:1", 2),
        make_user_message("hello", 3),
        make_connection_changed("connected", None, 4),
        make_agent_spawned("delegated:1", "delegated", "Worker", "lobby", 5),
        make_conversation_delta("hi", "message-1", 6),
        make_conversation_completed({"run_id": "run-1", "output": "done"}, 7),
        make_approval_requested({"run_id": "run-1", "approval_id": "approval-1"}, "yume", 8),
        make_run_finished({"run_id": "run-1"}, "completed", 9),
        make_snapshot_event(WorldReducer().snapshot),
    ],
)
def test_event_factory_output_validates_against_discriminated_union(event: WorldEvent) -> None:
    assert TypeAdapter(WorldEvent).validate_python(event.model_dump()) == event


def test_factories_truncate_only_user_visible_summaries() -> None:
    long_text = "x" * 241

    agent = make_agent_state("yume", "working", "work", 1, task_summary=long_text)
    approval = make_approval_requested(
        {"run_id": "run-1", "approval_id": "approval-1", "prompt": long_text}, "yume", 2
    )
    finished = make_run_finished({"run_id": "run-1", "error": long_text}, "failed", 3)

    assert len(agent.payload.task_summary or "") == 240
    assert len(approval.payload.prompt) == 240
    assert len(finished.payload.error or "") == 240


def test_completed_conversation_uses_empty_text_when_hermes_has_no_output() -> None:
    completed = make_conversation_completed({"run_id": "run-1", "output": None}, 1)

    assert completed.payload.message_id == "run-1"
    assert completed.payload.text == ""


def test_agent_spawned_optional_fields_are_keyword_only() -> None:
    spawned_factory = cast("Any", make_agent_spawned)
    with pytest.raises(TypeError):
        spawned_factory("delegated:1", "delegated", "Worker", "lobby", 1, "Task")
