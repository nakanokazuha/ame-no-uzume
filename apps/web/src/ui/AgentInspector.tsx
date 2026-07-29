import type { AgentView } from "@yume/contracts";
import { useEffect, useState, type JSX } from "react";

const labels = {
  kind: {
    yume: "CEO",
    scheduled: "Scheduled worker",
    delegated: "Delegated worker",
  },
  room: {
    ceo: "CEO office",
    memory: "Memory vault",
    research: "Research library",
    work: "Work floor",
    automation: "Automation bay",
    lobby: "Lobby",
  },
} as const;

export interface AgentInspectorProps {
  agent: AgentView;
  onClose: () => void;
}

function humanizeKind(kind: AgentView["kind"]): string {
  return labels.kind[kind];
}

function humanizeRoom(room: AgentView["room"]): string {
  return labels.room[room];
}

function humanizeStatus(status: AgentView["status"]): string {
  return status.replaceAll("_", " ");
}

function parsedTimestamp(iso: string | null | undefined): number | undefined {
  if (iso === null || iso === undefined) {
    return undefined;
  }

  const timestamp = Date.parse(iso);
  return Number.isFinite(timestamp) ? timestamp : undefined;
}

function formatElapsed(startedAt: string | null | undefined, now: number): string {
  if (startedAt === null || startedAt === undefined) {
    return "Not available";
  }

  const startedAtTimestamp = parsedTimestamp(startedAt);
  if (startedAtTimestamp === undefined) {
    return "Unknown";
  }

  const elapsedSeconds = Math.floor((now - startedAtTimestamp) / 1_000);
  if (elapsedSeconds < 0) {
    return "Not started";
  }

  const hours = Math.floor(elapsedSeconds / 3_600);
  const minutes = Math.floor((elapsedSeconds % 3_600) / 60);
  const seconds = elapsedSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function formatTime(iso: string): string | undefined {
  const timestamp = parsedTimestamp(iso);
  if (timestamp === undefined) {
    return undefined;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(timestamp);
}

export function AgentInspector({
  agent,
  onClose,
}: AgentInspectorProps): JSX.Element {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (parsedTimestamp(agent.started_at) === undefined) {
      return undefined;
    }

    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [agent.started_at]);

  const nextRun = agent.next_run_at ? formatTime(agent.next_run_at) : undefined;

  return (
    <aside
      aria-label={`${agent.display_name} details`}
      className="agent-inspector"
    >
      <button aria-label="Close agent details" onClick={onClose} type="button">
        ×
      </button>
      <h2>{agent.display_name}</h2>
      <dl>
        <dt>Role</dt>
        <dd>{humanizeKind(agent.kind)}</dd>
        <dt>Status</dt>
        <dd>{humanizeStatus(agent.status)}</dd>
        <dt>Room</dt>
        <dd>{humanizeRoom(agent.room)}</dd>
        <dt>Evidence</dt>
        <dd>{agent.evidence === "verified" ? "Verified" : "Inferred"}</dd>
        <dt>Elapsed</dt>
        <dd>{formatElapsed(agent.started_at, now)}</dd>
        {agent.evidence === "verified" && agent.task_summary && (
          <>
            <dt>Task</dt>
            <dd>{agent.task_summary}</dd>
          </>
        )}
        {agent.next_run_at && (
          <>
            <dt>Next run</dt>
            <dd>
              {nextRun ? (
                <time dateTime={agent.next_run_at}>{nextRun}</time>
              ) : (
                "Unknown"
              )}
            </dd>
          </>
        )}
      </dl>
    </aside>
  );
}
