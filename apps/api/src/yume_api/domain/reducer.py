"""Authoritative immutable-copy reducer for the dashboard world snapshot."""

from collections import OrderedDict

from yume_api.contracts.events import (
    AgentRemovedEvent,
    AgentSpawnedEvent,
    AgentStateChangedEvent,
    AgentTaskChangedEvent,
    AgentView,
    ConversationMessage,
    WorldEvent,
    WorldSnapshot,
)

STREAM_DELEGATED_PREFIX = "stream-delegated:"
MAX_HOOK_TERMINAL_AGENT_IDS = 1_000


class WorldReducer:
    """Apply world events while keeping Yume persistent and callers isolated."""

    def __init__(self) -> None:
        self._snapshot = WorldSnapshot(
            sequence=0,
            connection="starting",
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
        self._hook_owned_agent_ids: set[str] = set()
        self._hook_terminal_agent_ids: OrderedDict[str, None] = OrderedDict()

    @property
    def snapshot(self) -> WorldSnapshot:
        """Return an isolated deep copy of the current authoritative world."""
        return self._snapshot.model_copy(deep=True)

    def apply(self, event: WorldEvent) -> WorldSnapshot:
        """Apply one event and return an independent snapshot copy."""
        if event.type == "snapshot.replaced":
            self._snapshot = event.payload.snapshot.model_copy(deep=True)
            snapshot_agent_ids = {agent.agent_id for agent in self._snapshot.agents}
            self._hook_owned_agent_ids.intersection_update(snapshot_agent_ids)
            for agent_id in snapshot_agent_ids:
                self._hook_terminal_agent_ids.pop(agent_id, None)
            return self.snapshot
        if event.sequence <= self._snapshot.sequence:
            return self.snapshot

        if self._is_hook_owned_stream_event(event):
            return self.snapshot

        agents = {agent.agent_id: agent for agent in self._snapshot.agents}
        conversation = list(self._snapshot.conversation)
        connection = self._snapshot.connection

        if event.type == "agent.spawned":
            self._prepare_hook_spawn(event, agents)
            agents[event.agent_id] = AgentView(
                agent_id=event.agent_id,
                evidence=event.evidence,
                **event.payload.model_dump(),
            )
        elif event.type == "agent.state_changed" and event.agent_id in agents:
            agents[event.agent_id] = agents[event.agent_id].model_copy(
                update=event.payload.model_dump(exclude_none=True)
            )
        elif event.type == "agent.removed" and event.agent_id != "yume":
            agents.pop(event.agent_id, None)
            self._record_hook_removal(event)
        elif event.type == "connection.changed":
            connection = event.payload.status
        elif event.type == "conversation.user_added":
            conversation.append(
                ConversationMessage(
                    message_id=event.payload.message_id,
                    role="user",
                    text=event.payload.text,
                )
            )
        elif event.type == "conversation.completed":
            conversation.append(
                ConversationMessage(
                    message_id=event.payload.message_id,
                    role="assistant",
                    text=event.payload.text,
                )
            )

        self._snapshot = WorldSnapshot(
            sequence=event.sequence,
            connection=connection,
            telemetry_mode=self._snapshot.telemetry_mode,
            session_id=self._snapshot.session_id,
            agents=list(agents.values()),
            conversation=conversation,
        )
        return self.snapshot

    def _is_hook_owned_stream_event(self, event: WorldEvent) -> bool:
        """Return whether a generic stream event must not overwrite hook facts."""
        if event.source != "hermes.session_stream":
            return False
        if not isinstance(
            event,
            (AgentSpawnedEvent, AgentStateChangedEvent, AgentTaskChangedEvent, AgentRemovedEvent),
        ):
            return False
        if self._snapshot.telemetry_mode == "enhanced" and event.agent_id.startswith(
            STREAM_DELEGATED_PREFIX
        ):
            return True
        return (
            event.agent_id in self._hook_owned_agent_ids
            or event.agent_id in self._hook_terminal_agent_ids
        )

    def _prepare_hook_spawn(self, event: AgentSpawnedEvent, agents: dict[str, AgentView]) -> None:
        """Open a verified lifecycle and discard generic placeholders in enhanced mode."""
        if event.source != "hermes.hook":
            return
        if self._snapshot.telemetry_mode == "enhanced":
            for agent_id in tuple(agents):
                if agent_id.startswith(STREAM_DELEGATED_PREFIX):
                    agents.pop(agent_id)
        self._hook_terminal_agent_ids.pop(event.agent_id, None)
        self._hook_owned_agent_ids.add(event.agent_id)

    def _record_hook_removal(self, event: AgentRemovedEvent) -> None:
        """Remember a verified terminal lifecycle until a fresh hook start reopens it."""
        if event.source != "hermes.hook":
            return
        self._hook_owned_agent_ids.discard(event.agent_id)
        self._record_hook_terminal_agent(event.agent_id)

    def _record_hook_terminal_agent(self, agent_id: str) -> None:
        """Retain a bounded tombstone so delayed stream telemetry cannot resurrect it."""
        self._hook_terminal_agent_ids[agent_id] = None
        self._hook_terminal_agent_ids.move_to_end(agent_id)
        if len(self._hook_terminal_agent_ids) > MAX_HOOK_TERMINAL_AGENT_IDS:
            self._hook_terminal_agent_ids.popitem(last=False)
