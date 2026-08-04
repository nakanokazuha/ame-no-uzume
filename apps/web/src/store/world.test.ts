import { describe, expect, it } from "vitest";
import { createWorldStore } from "./world";

const baseEvent = {
  event_id: "event-1",
  occurred_at: "2026-07-29T00:00:00Z",
  source: "test",
  evidence: "verified" as const,
};

const yumeAgent = {
  agent_id: "yume",
  kind: "yume" as const,
  display_name: "Yume",
  status: "idle" as const,
  room: "ceo" as const,
  evidence: "verified" as const,
};

describe("world store", () => {
  it("rejects an event whose sequence is not newer than the current snapshot", () => {
    const store = createWorldStore();

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "snapshot-5",
      sequence: 5,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 5,
          connection: "connected",
          telemetry_mode: "enhanced",
          session_id: "session-1",
          agents: [yumeAgent],
          conversation: [],
        },
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "stale-5",
      sequence: 5,
      type: "connection.changed",
      payload: { status: "disconnected" },
    });

    expect(store.getState()).toMatchObject({ sequence: 5, connection: "connected" });
  });

  it("keeps the newer authoritative snapshot when a stale snapshot arrives", () => {
    const store = createWorldStore();

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "snapshot-9",
      sequence: 9,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 9,
          connection: "connected",
          telemetry_mode: "enhanced",
          session_id: "session-newer",
          agents: [yumeAgent],
          conversation: [],
        },
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "snapshot-5",
      sequence: 5,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 5,
          connection: "disconnected",
          telemetry_mode: "standard",
          session_id: "session-stale",
          agents: [],
          conversation: [],
        },
      },
    });

    expect(store.getState()).toMatchObject({
      sequence: 9,
      connection: "connected",
      session_id: "session-newer",
      agents: [yumeAgent],
    });
  });

  it("replaces all authoritative fields when it receives a snapshot", () => {
    const store = createWorldStore();
    store.getState().selectAgent("yume");
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "snapshot-9",
      sequence: 9,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 9,
          connection: "degraded",
          telemetry_mode: "standard",
          session_id: null,
          agents: [yumeAgent],
          conversation: [{ message_id: "user-1", role: "user", text: "Hello" }],
        },
      },
    });

    expect(store.getState()).toMatchObject({
      sequence: 9,
      connection: "degraded",
      telemetry_mode: "standard",
      session_id: null,
      agents: [yumeAgent],
      conversation: [{ message_id: "user-1", role: "user", text: "Hello" }],
      streamingText: "",
      selectedAgentId: "yume",
    });
  });

  it("accumulates assistant deltas then records their completed message", () => {
    const store = createWorldStore();

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "delta-1",
      sequence: 1,
      type: "conversation.delta",
      payload: { message_id: "assistant-1", text: "Hello" },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "delta-2",
      sequence: 2,
      type: "conversation.delta",
      payload: { message_id: "assistant-1", text: ", world" },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "completed-3",
      sequence: 3,
      type: "conversation.completed",
      payload: { message_id: "assistant-1", text: "Hello, world" },
    });

    expect(store.getState().streamingText).toBe("");
    expect(store.getState().conversation).toEqual([
      { message_id: "assistant-1", role: "assistant", text: "Hello, world" },
    ]);
  });

  it("spawns, updates, and removes an ephemeral worker", () => {
    const store = createWorldStore();

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "spawn-1",
      sequence: 1,
      type: "agent.spawned",
      agent_id: "delegated:run-1:call-1",
      payload: {
        kind: "delegated",
        display_name: "Delegated worker",
        status: "entering",
        room: "lobby",
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "state-2",
      sequence: 2,
      type: "agent.state_changed",
      agent_id: "delegated:run-1:call-1",
      payload: { status: "working", room: "work", task_summary: "Inspect the task" },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "removed-3",
      sequence: 3,
      type: "agent.removed",
      agent_id: "delegated:run-1:call-1",
      payload: {},
    });

    expect(store.getState().agents).toEqual([]);
    expect(store.getState().sequence).toBe(3);
  });

  it.each(["stream-first", "hook-first"])(
    "keeps one enriched worker for the exact child ID when events arrive %s",
    (arrivalOrder) => {
      const store = createWorldStore();
      const streamEvent = {
        ...baseEvent,
        event_id: "stream-spawn",
        sequence: arrivalOrder === "stream-first" ? 1 : 2,
        source: "hermes.session_stream",
        type: "agent.spawned" as const,
        agent_id: "delegated:child-7",
        payload: {
          kind: "delegated" as const,
          display_name: "Delegated Worker",
          status: "entering" as const,
          room: "lobby" as const,
        },
      };
      const hookEvent = {
        ...baseEvent,
        event_id: "hook-spawn",
        sequence: arrivalOrder === "hook-first" ? 1 : 2,
        source: "hermes.hook",
        type: "agent.spawned" as const,
        agent_id: "delegated:child-7",
        payload: {
          kind: "delegated" as const,
          display_name: "Researcher",
          status: "entering" as const,
          room: "lobby" as const,
          task_summary: "Compare Hermes event hooks",
        },
      };

      if (arrivalOrder === "stream-first") {
        store.getState().applyEvent(streamEvent);
        store.getState().applyEvent(hookEvent);
      } else {
        store.getState().applyEvent(hookEvent);
        store.getState().applyEvent(streamEvent);
      }

      expect(store.getState().agents).toEqual([
        {
          agent_id: "delegated:child-7",
          kind: "delegated",
          display_name: "Researcher",
          status: "entering",
          room: "lobby",
          evidence: "verified",
          task_summary: "Compare Hermes event hooks",
        },
      ]);
    },
  );
});
