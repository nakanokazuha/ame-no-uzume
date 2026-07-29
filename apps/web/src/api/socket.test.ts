import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectWorldSocket } from "./socket";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  open(): void {
    this.onopen?.(new Event("open"));
  }

  receive(data: string): void {
    this.onmessage?.({ data } as MessageEvent);
  }

  disconnect(): void {
    this.onclose?.({} as CloseEvent);
  }
}

describe("world event socket", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("parses events and reconnects after a close using exponential backoff", () => {
    const onEvent = vi.fn();
    const onState = vi.fn();
    connectWorldSocket("ws://dashboard.test/api/events", onEvent, onState);

    const firstSocket = MockWebSocket.instances[0];
    expect(firstSocket?.url).toBe("ws://dashboard.test/api/events");
    firstSocket?.open();
    firstSocket?.receive(
      JSON.stringify({
        event_id: "event-1",
        sequence: 1,
        occurred_at: "2026-07-29T00:00:00Z",
        source: "test",
        evidence: "verified",
        type: "connection.changed",
        payload: { status: "connected" },
      }),
    );
    firstSocket?.disconnect();

    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ sequence: 1 }));
    expect(onState).toHaveBeenNthCalledWith(1, true);
    expect(onState).toHaveBeenNthCalledWith(2, false);

    vi.advanceTimersByTime(499);
    expect(MockWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(MockWebSocket.instances).toHaveLength(2);

    MockWebSocket.instances[1]?.open();
    MockWebSocket.instances[1]?.disconnect();
    vi.advanceTimersByTime(500);
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it("ignores valid JSON that is not a world event", () => {
    const onEvent = vi.fn();
    connectWorldSocket("ws://dashboard.test/api/events", onEvent);

    const socket = MockWebSocket.instances[0];
    socket?.receive("{}");
    socket?.receive(JSON.stringify({ type: "not.a.world.event", payload: {} }));

    expect(onEvent).not.toHaveBeenCalled();
  });

  it("cancels a pending reconnect and closes the active socket", () => {
    const disconnect = connectWorldSocket("ws://dashboard.test/api/events", vi.fn());
    const socket = MockWebSocket.instances[0];
    socket?.disconnect();

    disconnect();
    vi.advanceTimersByTime(10_000);

    expect(socket?.close).toHaveBeenCalledOnce();
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("does not emit a transport state update after intentional cleanup", () => {
    const onState = vi.fn();
    const disconnect = connectWorldSocket("ws://dashboard.test/api/events", vi.fn(), onState);
    const socket = MockWebSocket.instances[0];

    socket?.open();
    disconnect();
    socket?.disconnect();

    expect(onState).toHaveBeenCalledExactlyOnceWith(true);
    vi.advanceTimersByTime(10_000);
    expect(MockWebSocket.instances).toHaveLength(1);
  });
});
