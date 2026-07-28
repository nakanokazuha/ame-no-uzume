"""Authoritative immutable-copy reducer for the dashboard world snapshot."""

from yume_api.contracts.events import AgentView, ConversationMessage, WorldEvent, WorldSnapshot


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

    @property
    def snapshot(self) -> WorldSnapshot:
        """Return an isolated deep copy of the current authoritative world."""
        return self._snapshot.model_copy(deep=True)

    def apply(self, event: WorldEvent) -> WorldSnapshot:
        """Apply one event and return an independent snapshot copy."""
        if event.type == "snapshot.replaced":
            self._snapshot = event.payload.snapshot.model_copy(deep=True)
            return self.snapshot

        agents = {agent.agent_id: agent for agent in self._snapshot.agents}
        conversation = list(self._snapshot.conversation)
        connection = self._snapshot.connection

        if event.type == "agent.spawned":
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
