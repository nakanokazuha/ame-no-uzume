from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

EvidenceLevel = Literal["verified", "inferred"]
AgentKind = Literal["yume", "scheduled", "delegated"]
AgentStatus = Literal[
    "idle",
    "entering",
    "thinking",
    "moving",
    "working",
    "waiting_approval",
    "completed",
    "failed",
    "exiting",
    "stale",
]
RoomId = Literal["ceo", "memory", "research", "work", "automation", "lobby"]
ConnectionStatus = Literal["starting", "connected", "degraded", "disconnected"]


class AgentView(BaseModel):
    agent_id: str
    kind: AgentKind
    display_name: str
    status: AgentStatus
    room: RoomId
    evidence: EvidenceLevel
    task_summary: str | None = None
    started_at: datetime | None = None
    next_run_at: datetime | None = None


class ConversationMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    text: str


class WorldSnapshot(BaseModel):
    sequence: int
    connection: ConnectionStatus
    telemetry_mode: Literal["standard", "enhanced"] = "standard"
    session_id: str | None = None
    agents: list[AgentView]
    conversation: list[ConversationMessage] = Field(default_factory=list)


class EventBase(BaseModel):
    schema_version: Literal[1] = 1
    event_id: str
    sequence: int
    occurred_at: datetime
    source: str
    evidence: EvidenceLevel


class AgentSpawnedPayload(BaseModel):
    kind: AgentKind
    display_name: str
    status: AgentStatus
    room: RoomId
    task_summary: str | None = None
    started_at: datetime | None = None
    next_run_at: datetime | None = None


class AgentSpawnedEvent(EventBase):
    type: Literal["agent.spawned"]
    agent_id: str
    payload: AgentSpawnedPayload


class AgentStatePayload(BaseModel):
    status: AgentStatus
    room: RoomId
    task_summary: str | None = None
    next_run_at: datetime | None = None


class AgentStateChangedEvent(EventBase):
    type: Literal["agent.state_changed"]
    agent_id: str
    payload: AgentStatePayload


class AgentRemovedEvent(EventBase):
    type: Literal["agent.removed"]
    agent_id: str
    payload: dict[str, str] = Field(default_factory=dict)


class ConnectionPayload(BaseModel):
    status: ConnectionStatus
    reason: str | None = None


class ConnectionChangedEvent(EventBase):
    type: Literal["connection.changed"]
    payload: ConnectionPayload


class SnapshotPayload(BaseModel):
    snapshot: WorldSnapshot


class SnapshotReplacedEvent(EventBase):
    type: Literal["snapshot.replaced"]
    payload: SnapshotPayload


class ConversationPayload(BaseModel):
    text: str
    message_id: str


class ConversationDeltaEvent(EventBase):
    type: Literal["conversation.delta"]
    payload: ConversationPayload


class ConversationUserAddedEvent(EventBase):
    type: Literal["conversation.user_added"]
    payload: ConversationPayload


class ConversationCompletedEvent(EventBase):
    type: Literal["conversation.completed"]
    payload: ConversationPayload


class ApprovalPayload(BaseModel):
    run_id: str
    approval_id: str
    prompt: str


class ApprovalRequestedEvent(EventBase):
    type: Literal["approval.requested"]
    agent_id: str
    payload: ApprovalPayload


class ApprovalResolvedEvent(EventBase):
    type: Literal["approval.resolved"]
    agent_id: str
    payload: dict[str, str]


class RunFinishedPayload(BaseModel):
    run_id: str
    outcome: Literal["completed", "failed", "cancelled"]
    error: str | None = None


class RunFinishedEvent(EventBase):
    type: Literal["run.finished"]
    payload: RunFinishedPayload


WorldEvent = Annotated[
    AgentSpawnedEvent
    | AgentStateChangedEvent
    | AgentRemovedEvent
    | ConnectionChangedEvent
    | SnapshotReplacedEvent
    | ConversationUserAddedEvent
    | ConversationDeltaEvent
    | ConversationCompletedEvent
    | ApprovalRequestedEvent
    | ApprovalResolvedEvent
    | RunFinishedEvent,
    Field(discriminator="type"),
]
