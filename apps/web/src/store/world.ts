import { createStore, type StoreApi } from "zustand/vanilla";
import type { AgentView, ConversationMessage, WorldEvent, WorldSnapshot } from "@yume/contracts";

export type WorldState = WorldSnapshot & {
  telemetry_mode: NonNullable<WorldSnapshot["telemetry_mode"]>;
  session_id: NonNullable<WorldSnapshot["session_id"]> | null;
  conversation: ConversationMessage[];
  streamingText: string;
  streamingMessageId: string | null;
  selectedAgentId: string | null;
  hookOwnedAgentIds: ReadonlySet<string>;
  applyEvent: (event: WorldEvent) => void;
  selectAgent: (agentId: string | null) => void;
};

const initialWorldState: Pick<
  WorldState,
  | "sequence"
  | "connection"
  | "telemetry_mode"
  | "session_id"
  | "agents"
  | "conversation"
  | "streamingText"
  | "streamingMessageId"
  | "selectedAgentId"
  | "hookOwnedAgentIds"
> = {
  sequence: 0,
  connection: "starting",
  telemetry_mode: "standard",
  session_id: null,
  agents: [],
  conversation: [],
  streamingText: "",
  streamingMessageId: null,
  selectedAgentId: null,
  hookOwnedAgentIds: new Set(),
};

function replaceSnapshot(state: WorldState, snapshot: WorldSnapshot): WorldState {
  return {
    ...state,
    sequence: snapshot.sequence,
    connection: snapshot.connection,
    telemetry_mode: snapshot.telemetry_mode ?? "standard",
    session_id: snapshot.session_id ?? null,
    agents: snapshot.agents,
    conversation: snapshot.conversation ?? [],
    streamingText: "",
    streamingMessageId: null,
    hookOwnedAgentIds: new Set(
      [...state.hookOwnedAgentIds].filter((agentId) =>
        snapshot.agents.some((agent) => agent.agent_id === agentId),
      ),
    ),
  };
}

function withSequence(state: WorldState, sequence: number): WorldState {
  return { ...state, sequence };
}

function hasAgentId(event: WorldEvent): event is Extract<WorldEvent, { agent_id: string }> {
  return "agent_id" in event && typeof event.agent_id === "string";
}

function isHookOwnedStreamEvent(state: WorldState, event: WorldEvent): boolean {
  return (
    event.source === "hermes.session_stream" &&
    hasAgentId(event) &&
    state.hookOwnedAgentIds.has(event.agent_id)
  );
}

export function reduceWorldEvent(state: WorldState, event: WorldEvent): WorldState {
  if (event.sequence <= state.sequence) {
    return state;
  }
  if (event.type === "snapshot.replaced") {
    return replaceSnapshot(state, event.payload.snapshot);
  }

  switch (event.type) {
    case "connection.changed":
      return { ...withSequence(state, event.sequence), connection: event.payload.status };
    case "conversation.delta": {
      const isSameMessage = state.streamingMessageId === event.payload.message_id;
      return {
        ...withSequence(state, event.sequence),
        streamingText: isSameMessage ? state.streamingText + event.payload.text : event.payload.text,
        streamingMessageId: event.payload.message_id,
      };
    }
    case "conversation.completed": {
      const message: ConversationMessage = {
        message_id: event.payload.message_id,
        role: "assistant",
        text: event.payload.text,
      };
      return {
        ...withSequence(state, event.sequence),
        conversation: [...state.conversation, message],
        streamingText: "",
        streamingMessageId: null,
      };
    }
    case "conversation.user_added": {
      const message: ConversationMessage = {
        message_id: event.payload.message_id,
        role: "user",
        text: event.payload.text,
      };
      return {
        ...withSequence(state, event.sequence),
        conversation: [...state.conversation, message],
      };
    }
    case "agent.spawned": {
      if (isHookOwnedStreamEvent(state, event)) {
        return withSequence(state, event.sequence);
      }
      const agent: AgentView = {
        agent_id: event.agent_id,
        evidence: event.evidence,
        ...event.payload,
      };
      return {
        ...withSequence(state, event.sequence),
        agents: [...state.agents.filter((current) => current.agent_id !== event.agent_id), agent],
        hookOwnedAgentIds:
          event.source === "hermes.hook"
            ? new Set([...state.hookOwnedAgentIds, event.agent_id])
            : state.hookOwnedAgentIds,
      };
    }
    case "agent.state_changed":
      if (isHookOwnedStreamEvent(state, event)) {
        return withSequence(state, event.sequence);
      }
      return {
        ...withSequence(state, event.sequence),
        agents: state.agents.map((agent) =>
          agent.agent_id === event.agent_id ? { ...agent, ...event.payload } : agent,
        ),
      };
    case "agent.task_changed":
      if (isHookOwnedStreamEvent(state, event)) {
        return withSequence(state, event.sequence);
      }
      return {
        ...withSequence(state, event.sequence),
        agents: state.agents.map((agent) =>
          agent.agent_id === event.agent_id
            ? { ...agent, task_summary: event.payload.task_summary }
            : agent,
        ),
      };
    case "agent.removed":
      if (isHookOwnedStreamEvent(state, event)) {
        return withSequence(state, event.sequence);
      }
      return {
        ...withSequence(state, event.sequence),
        agents: state.agents.filter((agent) => agent.agent_id !== event.agent_id),
        hookOwnedAgentIds:
          event.source === "hermes.hook"
            ? new Set(
                [...state.hookOwnedAgentIds].filter((agentId) => agentId !== event.agent_id),
              )
            : state.hookOwnedAgentIds,
      };
    case "approval.requested":
    case "approval.resolved":
    case "run.finished":
      return withSequence(state, event.sequence);
  }
}

export function createWorldStore(): StoreApi<WorldState> {
  return createStore<WorldState>((set) => ({
    ...initialWorldState,
    applyEvent: (event): void => {
      set((state) => reduceWorldEvent(state, event));
    },
    selectAgent: (selectedAgentId): void => {
      set({ selectedAgentId });
    },
  }));
}

export const useWorldStore = createWorldStore();
