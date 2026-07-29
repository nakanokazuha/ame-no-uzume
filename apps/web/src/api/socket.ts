import type { WorldEvent } from "@yume/contracts";

const INITIAL_RECONNECT_DELAY_MS = 500;
const MAX_RECONNECT_DELAY_MS = 10_000;

type ConnectionHandler = (connected: boolean) => void;

const connectionStatuses = ["starting", "connected", "degraded", "disconnected"] as const;
const evidenceLevels = ["verified", "inferred"] as const;
const agentKinds = ["yume", "scheduled", "delegated"] as const;
const agentStatuses = [
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
] as const;
const roomIds = ["ceo", "memory", "research", "work", "automation", "lobby"] as const;
const worldEventTypes = [
  "agent.spawned",
  "agent.state_changed",
  "agent.task_changed",
  "agent.removed",
  "connection.changed",
  "snapshot.replaced",
  "conversation.user_added",
  "conversation.delta",
  "conversation.completed",
  "approval.requested",
  "approval.resolved",
  "run.finished",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOneOf<T extends readonly string[]>(value: unknown, values: T): value is T[number] {
  return typeof value === "string" && values.includes(value);
}

function isSequence(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isOptionalStringOrNull(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return isRecord(value) && Object.values(value).every((entry) => typeof entry === "string");
}

function isAgentView(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value["agent_id"] === "string" &&
    isOneOf(value["kind"], agentKinds) &&
    typeof value["display_name"] === "string" &&
    isOneOf(value["status"], agentStatuses) &&
    isOneOf(value["room"], roomIds) &&
    isOneOf(value["evidence"], evidenceLevels) &&
    isOptionalStringOrNull(value["task_summary"]) &&
    isOptionalStringOrNull(value["started_at"]) &&
    isOptionalStringOrNull(value["next_run_at"])
  );
}

function isConversationMessage(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value["message_id"] === "string" &&
    (value["role"] === "user" || value["role"] === "assistant") &&
    typeof value["text"] === "string"
  );
}

function isSnapshot(value: unknown, eventSequence: number): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return (
    value["sequence"] === eventSequence &&
    isOneOf(value["connection"], connectionStatuses) &&
    (value["telemetry_mode"] === undefined ||
      value["telemetry_mode"] === "standard" ||
      value["telemetry_mode"] === "enhanced") &&
    isOptionalStringOrNull(value["session_id"]) &&
    Array.isArray(value["agents"]) &&
    value["agents"].every(isAgentView) &&
    (value["conversation"] === undefined ||
      (Array.isArray(value["conversation"]) && value["conversation"].every(isConversationMessage)))
  );
}

function isWorldEvent(value: unknown): value is WorldEvent {
  if (
    !isRecord(value) ||
    typeof value["event_id"] !== "string" ||
    !isSequence(value["sequence"]) ||
    typeof value["occurred_at"] !== "string" ||
    typeof value["source"] !== "string" ||
    !isOneOf(value["evidence"], evidenceLevels) ||
    !isOneOf(value["type"], worldEventTypes) ||
    !isRecord(value["payload"]) ||
    (value["schema_version"] !== undefined && value["schema_version"] !== 1)
  ) {
    return false;
  }

  const payload = value["payload"];
  switch (value["type"]) {
    case "agent.spawned":
      return (
        typeof value["agent_id"] === "string" &&
        isOneOf(payload["kind"], agentKinds) &&
        typeof payload["display_name"] === "string" &&
        isOneOf(payload["status"], agentStatuses) &&
        isOneOf(payload["room"], roomIds) &&
        isOptionalStringOrNull(payload["task_summary"]) &&
        isOptionalStringOrNull(payload["started_at"]) &&
        isOptionalStringOrNull(payload["next_run_at"])
      );
    case "agent.state_changed":
      return (
        typeof value["agent_id"] === "string" &&
        isOneOf(payload["status"], agentStatuses) &&
        isOneOf(payload["room"], roomIds) &&
        isOptionalStringOrNull(payload["task_summary"]) &&
        isOptionalStringOrNull(payload["next_run_at"])
      );
    case "agent.task_changed":
      return (
        typeof value["agent_id"] === "string" &&
        (typeof payload["task_summary"] === "string" || payload["task_summary"] === null)
      );
    case "agent.removed":
      return typeof value["agent_id"] === "string" && isStringRecord(payload);
    case "connection.changed":
      return (
        isOneOf(payload["status"], connectionStatuses) &&
        isOptionalStringOrNull(payload["reason"])
      );
    case "snapshot.replaced":
      return isSnapshot(payload["snapshot"], value["sequence"]);
    case "conversation.user_added":
    case "conversation.delta":
    case "conversation.completed":
      return typeof payload["message_id"] === "string" && typeof payload["text"] === "string";
    case "approval.requested":
      return (
        typeof value["agent_id"] === "string" &&
        typeof payload["run_id"] === "string" &&
        typeof payload["approval_id"] === "string" &&
        typeof payload["prompt"] === "string"
      );
    case "approval.resolved":
      return typeof value["agent_id"] === "string" && isStringRecord(payload);
    case "run.finished":
      return (
        typeof payload["run_id"] === "string" &&
        (payload["outcome"] === "completed" ||
          payload["outcome"] === "failed" ||
          payload["outcome"] === "cancelled") &&
        (payload["error"] === undefined ||
          payload["error"] === null ||
          typeof payload["error"] === "string")
      );
    default:
      return false;
  }
}

function parseWorldEvent(data: unknown): WorldEvent | undefined {
  if (typeof data !== "string") {
    return undefined;
  }

  try {
    const parsed: unknown = JSON.parse(data);
    return isWorldEvent(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

export function connectWorldSocket(
  url: string,
  onEvent: (event: WorldEvent) => void,
  onState: ConnectionHandler = () => undefined,
): () => void {
  let socket: WebSocket | undefined;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let cancelled = false;
  let reconnectDelay = INITIAL_RECONNECT_DELAY_MS;

  const connect = (): void => {
    if (cancelled) {
      return;
    }

    const nextSocket = new WebSocket(url);
    socket = nextSocket;

    nextSocket.onopen = (): void => {
      if (cancelled || socket !== nextSocket) {
        return;
      }
      reconnectDelay = INITIAL_RECONNECT_DELAY_MS;
      onState(true);
    };
    nextSocket.onmessage = (message): void => {
      if (cancelled || socket !== nextSocket) {
        return;
      }
      const event = parseWorldEvent(message.data);
      if (event) {
        onEvent(event);
      }
    };
    nextSocket.onclose = (): void => {
      if (cancelled || socket !== nextSocket) {
        return;
      }
      onState(false);

      const delay = reconnectDelay;
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = undefined;
        connect();
      }, delay);
    };
  };

  connect();

  return (): void => {
    cancelled = true;
    if (reconnectTimer !== undefined) {
      clearTimeout(reconnectTimer);
      reconnectTimer = undefined;
    }
    socket?.close();
  };
}
