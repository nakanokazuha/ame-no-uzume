import { describe, expect, it } from "vitest";
import type { AgentView } from "@yume/contracts";
import { animationKey, movementTargetPositions, needsStatusMarker, snapToPixel } from "./sprites";

const delegatedWorker: AgentView = {
  agent_id: "worker-1",
  display_name: "Worker",
  evidence: "verified",
  kind: "delegated",
  room: "work",
  status: "working",
};

describe("sprite helpers", () => {
  it("maps delegated work to the worker animation", () => {
    expect(animationKey(delegatedWorker, { "worker-work-sw": [22, 23] })).toBe(
      "worker-work-sw",
    );
  });

  it("falls back to an idle animation when a status animation is absent", () => {
    expect(
      animationKey(
        { ...delegatedWorker, status: "failed" },
        { "worker-idle-sw": [0, 1] },
      ),
    ).toBe("worker-idle-sw");
  });

  it("marks agents whose state needs an explicit status signal", () => {
    expect(needsStatusMarker({ ...delegatedWorker, status: "waiting_approval" })).toBe(true);
    expect(needsStatusMarker({ ...delegatedWorker, status: "stale" })).toBe(true);
    expect(needsStatusMarker(delegatedWorker)).toBe(false);
  });

  it("keeps an agent at its destination while placing its status marker above it", () => {
    expect(movementTargetPositions({ x: 184, y: 95 })).toEqual({
      sprite: { x: 184, y: 95 },
      marker: { x: 184, y: 43 },
    });
  });

  it("snaps rendered coordinates to whole pixels", () => {
    expect(snapToPixel({ x: 10.6, y: -2.5 })).toEqual({ x: 11, y: -2 });
  });
});
