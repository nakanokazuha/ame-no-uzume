"""Verified-first translation from Hermes stream events to world events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from yume_api.contracts.factories import (
    make_agent_removed,
    make_agent_spawned,
    make_agent_state,
    make_approval_requested,
    make_conversation_completed,
    make_conversation_delta,
    make_run_finished,
)

EXPLICIT_DELEGATED_PREFIX = "delegated:"
STREAM_DELEGATED_PREFIX = "stream-delegated:"

if TYPE_CHECKING:
    from collections.abc import Callable

    from yume_api.contracts.events import AgentSpawnedEvent, WorldEvent
    from yume_api.domain.room_policy import RoomPolicy
    from yume_api.hermes.models import HermesStreamEvent
    from yume_api.integrations.hook_models import HookEnvelope


def delegated_agent_id(data: dict[str, Any]) -> str | None:
    """Return an explicit child ID or a disjoint generic stream identity."""
    child_subagent_id = data.get("child_subagent_id")
    if isinstance(child_subagent_id, str) and child_subagent_id:
        return f"{EXPLICIT_DELEGATED_PREFIX}{child_subagent_id}"
    run_id = data.get("run_id")
    tool_call_id = data.get("tool_call_id")
    if not run_id or not tool_call_id:
        return None
    return f"{STREAM_DELEGATED_PREFIX}{run_id}:{tool_call_id}"


def is_delegated_agent_id(agent_id: str) -> bool:
    """Return whether an ID belongs to either delegated-worker namespace."""
    return agent_id.startswith((EXPLICIT_DELEGATED_PREFIX, STREAM_DELEGATED_PREFIX))


def agent_id_from(data: dict[str, Any]) -> str | None:
    """Return a supplied agent ID or a complete delegated worker ID."""
    agent_id = data.get("agent_id")
    return str(agent_id) if agent_id else delegated_agent_id(data)


def make_delegated_spawn(data: dict[str, Any], sequence: int) -> AgentSpawnedEvent | None:
    """Create a generic worker only when Hermes exposed a complete delegation identity."""
    agent_id = delegated_agent_id(data)
    if agent_id is None:
        return None
    task_summary = data.get("task_summary")
    return make_agent_spawned(
        agent_id,
        "delegated",
        "Delegated Worker",
        "lobby",
        sequence,
        task_summary=str(task_summary) if task_summary is not None else None,
    )


def humanize_role(role: str) -> str:
    """Turn a hook-supplied role identifier into a concise display name."""
    return role.replace("_", " ").title()


def make_subagent_exit_events(
    agent_id: str, *, failed: bool, sequence: int, source: str
) -> list[WorldEvent]:
    """Create the terminal lifecycle events for a hook-observed worker."""
    return [
        make_agent_state(
            agent_id,
            "failed" if failed else "completed",
            "work",
            sequence,
            source=source,
        ),
        make_agent_removed(agent_id, sequence + 1, source=source),
    ]


class HermesNormalizer:
    """Map known Hermes activity to verified dashboard events without speculation."""

    def __init__(self, room_policy: RoomPolicy) -> None:
        self._rooms = room_policy
        self._native_assistant_text = ""
        self._handlers: dict[str, Callable[[dict[str, Any], int], list[WorldEvent]]] = {
            "assistant.delta": self._assistant_delta,
            "assistant.completed": self._assistant_completed,
            "tool.started": self._tool_started,
            "tool.completed": self._tool_completed,
            "approval.requested": self._approval_requested,
            "run.completed": self._run_completed,
            "run.failed": self._run_failed,
            "run.cancelled": self._run_cancelled,
        }

    def normalize(self, event: HermesStreamEvent, sequence: int) -> list[WorldEvent]:
        """Normalize one Hermes event, ignoring unknown or incomplete telemetry."""
        handler = self._handlers.get(event.event)
        return handler(event.data, sequence) if handler else []

    def normalize_hook(self, envelope: HookEnvelope, sequence: int) -> list[WorldEvent]:
        """Normalize one bounded lifecycle hook into verified worker telemetry."""
        child_id = envelope.extra.get("child_subagent_id")
        if child_id is None:
            return []
        agent_id = f"{EXPLICIT_DELEGATED_PREFIX}{child_id}"
        if envelope.event == "subagent_start":
            role = envelope.extra.get("child_role")
            return [
                make_agent_spawned(
                    agent_id,
                    "delegated",
                    humanize_role(role) if role else "Delegated Worker",
                    "lobby",
                    sequence,
                    task_summary=envelope.extra.get("child_goal"),
                    source="hermes.hook",
                )
            ]
        status = envelope.extra.get("child_status")
        if status is None:
            return []
        return make_subagent_exit_events(
            agent_id,
            failed=status != "completed",
            sequence=sequence,
            source="hermes.hook",
        )

    def reset(self) -> None:
        """Discard native assistant text accumulated for the current task stream."""
        self._native_assistant_text = ""

    def _assistant_delta(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        message_id = data.get("message_id")
        text = data.get("delta", data.get("text", ""))
        if not message_id:
            self._native_assistant_text += "" if text is None else str(text)
            return []
        return [
            make_conversation_delta(
                text="" if text is None else str(text),
                message_id=str(message_id),
                sequence=sequence,
            )
        ]

    def _assistant_completed(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        message_id = data.get("message_id")
        completion_text = data.get("output")
        if completion_text is None:
            completion_text = data.get("text", self._native_assistant_text)
        self.reset()
        yume_idle = make_agent_state("yume", "idle", "ceo", sequence + 1)
        if not message_id:
            return [yume_idle]
        return [
            make_conversation_completed(
                {"message_id": message_id, "output": completion_text}, sequence
            ),
            yume_idle,
        ]

    def _tool_started(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        tool_name = data.get("tool_name")
        if not tool_name:
            return []
        if tool_name == "delegate_task":
            spawned = make_delegated_spawn(data, sequence)
            return [spawned] if spawned is not None else []
        return [make_agent_state("yume", "working", self._rooms.resolve(str(tool_name)), sequence)]

    def _tool_completed(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        agent_id = delegated_agent_id(data)
        if agent_id is None:
            return [make_agent_state("yume", "thinking", "ceo", sequence)]
        return [
            make_agent_state(agent_id, "completed", "work", sequence),
            make_agent_removed(agent_id, sequence + 1),
        ]

    def _approval_requested(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        if not data.get("run_id") or not data.get("approval_id"):
            return []
        agent_id = agent_id_from(data) or "yume"
        return [
            make_agent_state(agent_id, "waiting_approval", "work", sequence),
            make_approval_requested(data, agent_id, sequence + 1),
        ]

    def _run_completed(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        if not data.get("run_id"):
            return []
        self.reset()
        return [
            make_conversation_completed(data, sequence),
            make_run_finished(data, "completed", sequence + 1),
            make_agent_state("yume", "idle", "ceo", sequence + 2),
        ]

    def _run_failed(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        return self._terminal_run(data, "failed", sequence)

    def _run_cancelled(self, data: dict[str, Any], sequence: int) -> list[WorldEvent]:
        return self._terminal_run(data, "cancelled", sequence)

    def _terminal_run(
        self,
        data: dict[str, Any],
        outcome: Literal["failed", "cancelled"],
        sequence: int,
    ) -> list[WorldEvent]:
        if not data.get("run_id"):
            return []
        self.reset()
        events: list[WorldEvent] = [make_run_finished(data, outcome, sequence)]
        agent_id = agent_id_from(data)
        if agent_id and agent_id != "yume":
            events.append(make_agent_state(agent_id, "failed", "work", sequence + len(events)))
            if is_delegated_agent_id(agent_id):
                events.append(make_agent_removed(agent_id, sequence + len(events)))
        events.append(make_agent_state("yume", "idle", "ceo", sequence + len(events)))
        return events
