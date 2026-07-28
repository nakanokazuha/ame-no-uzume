"""Typed constructors for dashboard world events."""

# ruff: noqa: PLR0913, PLR0917

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from yume_api.contracts.events import (
    AgentKind,
    AgentRemovedEvent,
    AgentSpawnedEvent,
    AgentSpawnedPayload,
    AgentStateChangedEvent,
    AgentStatePayload,
    AgentStatus,
    ApprovalPayload,
    ApprovalRequestedEvent,
    ConnectionChangedEvent,
    ConnectionPayload,
    ConnectionStatus,
    ConversationCompletedEvent,
    ConversationDeltaEvent,
    ConversationPayload,
    ConversationUserAddedEvent,
    EvidenceLevel,
    RoomId,
    RunFinishedEvent,
    RunFinishedPayload,
    SnapshotPayload,
    SnapshotReplacedEvent,
    WorldSnapshot,
)

MAX_USER_VISIBLE_SUMMARY_LENGTH = 240


def _bounded_summary(value: str | None) -> str | None:
    return value[:MAX_USER_VISIBLE_SUMMARY_LENGTH] if value else None


def make_agent_state(
    agent_id: str,
    status: AgentStatus,
    room: RoomId,
    sequence: int,
    *,
    evidence: EvidenceLevel = "verified",
    task_summary: str | None = None,
    next_run_at: datetime | None = None,
) -> AgentStateChangedEvent:
    """Create a state update for an already-known agent."""
    return AgentStateChangedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="hermes.session_stream",
        evidence=evidence,
        type="agent.state_changed",
        agent_id=agent_id,
        payload=AgentStatePayload(
            status=status,
            room=room,
            task_summary=_bounded_summary(task_summary),
            next_run_at=next_run_at,
        ),
    )


def make_agent_removed(agent_id: str, sequence: int) -> AgentRemovedEvent:
    """Create a verified removal event for an ephemeral agent."""
    return AgentRemovedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="hermes.session_stream",
        evidence="verified",
        type="agent.removed",
        agent_id=agent_id,
        payload={},
    )


def make_user_message(text: str, sequence: int) -> ConversationUserAddedEvent:
    """Create a locally submitted user conversation message."""
    return ConversationUserAddedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="dashboard.user",
        evidence="verified",
        type="conversation.user_added",
        payload=ConversationPayload(text=text, message_id=str(uuid4())),
    )


def make_connection_changed(
    status: ConnectionStatus, reason: str | None, sequence: int
) -> ConnectionChangedEvent:
    """Create a verified adapter connection update."""
    return ConnectionChangedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="dashboard.adapter",
        evidence="verified",
        type="connection.changed",
        payload=ConnectionPayload(status=status, reason=reason),
    )


def make_agent_spawned(
    agent_id: str,
    kind: AgentKind,
    display_name: str,
    room: RoomId,
    sequence: int,
    task_summary: str | None = None,
    status: AgentStatus = "entering",
    next_run_at: datetime | None = None,
) -> AgentSpawnedEvent:
    """Create a verified agent spawn event."""
    now = datetime.now(UTC)
    return AgentSpawnedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=now,
        source="hermes.session_stream",
        evidence="verified",
        type="agent.spawned",
        agent_id=agent_id,
        payload=AgentSpawnedPayload(
            kind=kind,
            display_name=display_name,
            status=status,
            room=room,
            task_summary=_bounded_summary(task_summary),
            started_at=now,
            next_run_at=next_run_at,
        ),
    )


def make_conversation_delta(text: str, message_id: str, sequence: int) -> ConversationDeltaEvent:
    """Create a verified streamed assistant text delta."""
    return ConversationDeltaEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="hermes.session_stream",
        evidence="verified",
        type="conversation.delta",
        payload=ConversationPayload(text=text, message_id=message_id),
    )


def make_conversation_completed(data: dict[str, Any], sequence: int) -> ConversationCompletedEvent:
    """Create a verified completed assistant message from declared Hermes fields."""
    run_id = str(data["run_id"])
    message_id = str(data.get("message_id", run_id))
    return ConversationCompletedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="hermes.session_stream",
        evidence="verified",
        type="conversation.completed",
        payload=ConversationPayload(text=str(data.get("output", "")), message_id=message_id),
    )


def make_approval_requested(
    data: dict[str, Any], agent_id: str, sequence: int
) -> ApprovalRequestedEvent:
    """Create a verified approval request using only contract payload fields."""
    return ApprovalRequestedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="hermes.session_stream",
        evidence="verified",
        type="approval.requested",
        agent_id=agent_id,
        payload=ApprovalPayload(
            run_id=str(data["run_id"]),
            approval_id=str(data["approval_id"]),
            prompt=str(data.get("prompt", "Approval required"))[:MAX_USER_VISIBLE_SUMMARY_LENGTH],
        ),
    )


def make_run_finished(
    data: dict[str, Any], outcome: Literal["completed", "failed", "cancelled"], sequence: int
) -> RunFinishedEvent:
    """Create a verified terminal run event."""
    error = data.get("error")
    return RunFinishedEvent(
        event_id=str(uuid4()),
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        source="hermes.session_stream",
        evidence="verified",
        type="run.finished",
        payload=RunFinishedPayload(
            run_id=str(data["run_id"]),
            outcome=outcome,
            error=_bounded_summary(str(error)) if error else None,
        ),
    )


def make_snapshot_event(snapshot: WorldSnapshot) -> SnapshotReplacedEvent:
    """Create a replacement event from an authoritative snapshot copy."""
    return SnapshotReplacedEvent(
        event_id=str(uuid4()),
        sequence=snapshot.sequence,
        occurred_at=datetime.now(UTC),
        source="dashboard.snapshot",
        evidence="verified",
        type="snapshot.replaced",
        payload=SnapshotPayload(snapshot=snapshot.model_copy(deep=True)),
    )
