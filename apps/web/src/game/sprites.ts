import type { AgentView } from "@yume/contracts";
import type { WorldPoint } from "./coordinates";

type AnimationState =
  | "idle"
  | "enter"
  | "think"
  | "walk"
  | "work"
  | "waiting"
  | "report"
  | "failed"
  | "exit";

const statusAnimations: Record<AgentView["status"], AnimationState> = {
  idle: "idle",
  entering: "enter",
  thinking: "think",
  moving: "walk",
  working: "work",
  waiting_approval: "waiting",
  completed: "report",
  failed: "failed",
  exiting: "exit",
  stale: "waiting",
};

export function animationKey(agent: AgentView, animations: Record<string, number[]>): string {
  const role = agent.kind === "delegated" ? "worker" : agent.kind;
  const state = statusAnimations[agent.status];
  const preferred = `${role}-${state}-sw`;
  return animations[preferred] ? preferred : `${role}-idle-sw`;
}

export function needsStatusMarker(agent: AgentView): boolean {
  return agent.status === "waiting_approval" || agent.status === "stale";
}

export function statusMarkerPosition(point: WorldPoint): WorldPoint {
  return { x: point.x, y: point.y - 52 };
}

export function movementTargetPositions(point: WorldPoint): {
  sprite: WorldPoint;
  marker: WorldPoint;
} {
  return { sprite: { ...point }, marker: statusMarkerPosition(point) };
}

export function snapToPixel(point: WorldPoint): WorldPoint {
  return { x: Math.round(point.x), y: Math.round(point.y) };
}
