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

  it.each(["stream-first", "hook-first"])(
    "replaces generic stream placeholders with enhanced hook telemetry when events arrive %s",
    (arrivalOrder) => {
      const store = createWorldStore();
      const streamEvent = {
        ...baseEvent,
        event_id: "stream-fallback-spawn",
        sequence: arrivalOrder === "stream-first" ? 1 : 3,
        source: "hermes.session_stream",
        type: "agent.spawned" as const,
        agent_id: "stream-delegated:run-1:call-1",
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
        sequence: arrivalOrder === "hook-first" ? 2 : 3,
        source: "hermes.hook",
        type: "agent.spawned" as const,
        agent_id: "delegated:child-session-7",
        payload: {
          kind: "delegated" as const,
          display_name: "Researcher",
          status: "entering" as const,
          room: "lobby" as const,
          task_summary: "Keep this hook worker distinct",
        },
      };

      if (arrivalOrder === "stream-first") {
        store.getState().applyEvent(streamEvent);
        store.getState().applyEvent({
          ...baseEvent,
          event_id: "enhanced-snapshot",
          sequence: 2,
          type: "snapshot.replaced",
          payload: {
            snapshot: {
              sequence: 2,
              connection: "connected",
              telemetry_mode: "enhanced",
              agents: [
                {
                  agent_id: "stream-delegated:run-1:call-1",
                  kind: "delegated",
                  display_name: "Delegated Worker",
                  status: "entering",
                  room: "lobby",
                  evidence: "verified",
                },
              ],
            },
          },
        });
        store.getState().applyEvent(hookEvent);
      } else {
        store.getState().applyEvent({
          ...baseEvent,
          event_id: "enhanced-snapshot",
          sequence: 1,
          type: "snapshot.replaced",
          payload: {
            snapshot: {
              sequence: 1,
              connection: "connected",
              telemetry_mode: "enhanced",
              agents: [],
            },
          },
        });
        store.getState().applyEvent(hookEvent);
        store.getState().applyEvent(streamEvent);
      }

      expect(store.getState().agents).toEqual([
        expect.objectContaining({
          agent_id: "delegated:child-session-7",
          display_name: "Researcher",
        }),
      ]);
    },
  );

  it("blocks a delayed stream worker after hook removal until a new hook lifecycle starts", () => {
    const store = createWorldStore();
    const workerId = "delegated:child-session-7";

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "enhanced-snapshot",
      sequence: 1,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 1,
          connection: "connected",
          telemetry_mode: "enhanced",
          agents: [],
        },
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "hook-start",
      sequence: 2,
      source: "hermes.hook",
      type: "agent.spawned",
      agent_id: workerId,
      payload: {
        kind: "delegated",
        display_name: "Researcher",
        status: "entering",
        room: "lobby",
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "hook-stop",
      sequence: 3,
      source: "hermes.hook",
      type: "agent.removed",
      agent_id: workerId,
      payload: {},
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "replacement-snapshot",
      sequence: 4,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 4,
          connection: "connected",
          telemetry_mode: "enhanced",
          agents: [],
        },
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "delayed-stream-spawn",
      sequence: 5,
      source: "hermes.session_stream",
      type: "agent.spawned",
      agent_id: workerId,
      payload: {
        kind: "delegated",
        display_name: "Delegated Worker",
        status: "entering",
        room: "lobby",
      },
    });

    expect(store.getState().agents).toEqual([]);

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "reused-hook-start",
      sequence: 6,
      source: "hermes.hook",
      type: "agent.spawned",
      agent_id: workerId,
      payload: {
        kind: "delegated",
        display_name: "Researcher",
        status: "entering",
        room: "lobby",
      },
    });

    expect(store.getState().agents).toEqual([
      expect.objectContaining({ agent_id: workerId, display_name: "Researcher" }),
    ]);
  });

  it("evicts the oldest hook terminal tombstone at its bound", () => {
    const store = createWorldStore();
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "enhanced-snapshot",
      sequence: 1,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 1,
          connection: "connected",
          telemetry_mode: "enhanced",
          agents: [],
        },
      },
    });
    for (let index = 0; index < 1_001; index += 1) {
      store.getState().applyEvent({
        ...baseEvent,
        event_id: `hook-stop-${index}`,
        sequence: index + 2,
        source: "hermes.hook",
        type: "agent.removed",
        agent_id: `delegated:child-${index}`,
        payload: {},
      });
    }

    store.getState().applyEvent({
      ...baseEvent,
      event_id: "evicted-stream-spawn",
      sequence: 1_003,
      source: "hermes.session_stream",
      type: "agent.spawned",
      agent_id: "delegated:child-0",
      payload: {
        kind: "delegated",
        display_name: "Stream worker",
        status: "entering",
        room: "lobby",
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "retained-stream-spawn",
      sequence: 1_004,
      source: "hermes.session_stream",
      type: "agent.spawned",
      agent_id: "delegated:child-1",
      payload: {
        kind: "delegated",
        display_name: "Stream worker",
        status: "entering",
        room: "lobby",
      },
    });

    expect(store.getState().agents).toEqual([
      expect.objectContaining({ agent_id: "delegated:child-0" }),
    ]);
  });

  it("accepts an authoritative snapshot that reintroduces a tombstoned agent", () => {
    const store = createWorldStore();
    const workerId = "delegated:child-session-7";
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "enhanced-snapshot",
      sequence: 1,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 1,
          connection: "connected",
          telemetry_mode: "enhanced",
          agents: [],
        },
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "hook-stop",
      sequence: 2,
      source: "hermes.hook",
      type: "agent.removed",
      agent_id: workerId,
      payload: {},
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "authoritative-snapshot",
      sequence: 3,
      type: "snapshot.replaced",
      payload: {
        snapshot: {
          sequence: 3,
          connection: "connected",
          telemetry_mode: "enhanced",
          agents: [
            {
              agent_id: workerId,
              kind: "delegated",
              display_name: "Researcher",
              status: "working",
              room: "work",
              evidence: "verified",
            },
          ],
        },
      },
    });
    store.getState().applyEvent({
      ...baseEvent,
      event_id: "stream-state",
      sequence: 4,
      source: "hermes.session_stream",
      type: "agent.state_changed",
      agent_id: workerId,
      payload: { status: "completed", room: "work" },
    });

    expect(store.getState().agents).toEqual([
      expect.objectContaining({ agent_id: workerId, status: "completed" }),
    ]);
  });
});
