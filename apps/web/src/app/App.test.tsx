import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AgentView } from "@yume/contracts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BootstrapResponse } from "../api/client";
import { useWorldStore } from "../store/world";
import { App } from "./App";

vi.mock("../game/OfficeGame", () => ({
  OfficeGame: ({ bootstrap }: { bootstrap: BootstrapResponse }) => (
    <div
      aria-label={`Yume office using ${bootstrap.asset_pack.id}`}
      className="office"
      data-testid="office-canvas"
    />
  ),
}));

const initialWorldState = useWorldStore.getState();
const initialViewport = { height: window.innerHeight, width: window.innerWidth };

const yume: AgentView = {
  agent_id: "yume",
  display_name: "Yume",
  evidence: "verified",
  kind: "yume",
  room: "ceo",
  status: "working",
};

const delegatedWorker: AgentView = {
  agent_id: "worker-1",
  display_name: "Research worker",
  evidence: "verified",
  kind: "delegated",
  room: "research",
  status: "idle",
};

const bootstrap: BootstrapResponse = {
  world: {
    sequence: 4,
    connection: "degraded",
    telemetry_mode: "enhanced",
    session_id: "session-1",
    agents: [{ ...yume, status: "idle" }, delegatedWorker],
    conversation: [],
  },
  asset_pack: {
    id: "default",
    map: "/packs/default/map.json",
    atlas: "/packs/default/atlas.json",
    anchors: {},
    animations: {},
  },
};

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

function setViewport(width: number, height: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
});

afterEach(() => {
  cleanup();
  useWorldStore.setState(initialWorldState, true);
  setViewport(initialViewport.width, initialViewport.height);
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the office canvas and task control", () => {
    render(<App />);
    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Task Yume" })).toBeInTheDocument();
  });

  it("hydrates the office at the narrow boundary and applies authoritative socket events", async () => {
    setViewport(320, 260);
    useWorldStore.setState({
      agents: [delegatedWorker],
      selectedAgentId: delegatedWorker.agent_id,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(bootstrap), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      ),
    );

    const { unmount } = render(<App />);

    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "0px",
      top: "0px",
      width: "320px",
      height: "260px",
    });

    await waitFor(() => {
      expect(
        screen.getByRole("generic", { name: "Yume office using default" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Yume is idle")).toBeInTheDocument();
    expect(screen.getByText("Hermes disconnected")).toBeInTheDocument();
    expect(screen.getByText("2 agents")).toBeInTheDocument();
    expect(screen.getByText("Telemetry: enhanced")).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "Research worker details" }),
    ).toBeInTheDocument();
    expect(useWorldStore.getState().selectedAgentId).toBe(delegatedWorker.agent_id);

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });
    const socket = MockWebSocket.instances[0];
    expect(socket?.url).toMatch(/^ws:\/\/.*\/api\/events$/);

    act(() => {
      socket?.open();
    });
    expect(screen.getByText("Hermes disconnected")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();

    act(() => {
      socket?.receive(
        JSON.stringify({
          event_id: "connection-5",
          sequence: 5,
          occurred_at: "2026-07-29T00:00:00Z",
          source: "test",
          evidence: "verified",
          type: "connection.changed",
          payload: { status: "connected" },
        }),
      );
    });

    expect(screen.getByText("Hermes connected")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    unmount();
    expect(socket?.close).toHaveBeenCalledOnce();
  });

  it("waits for a validated socket resynchronization before exposing Hermes after reconnecting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...bootstrap,
            world: { ...bootstrap.world, connection: "connected" },
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 200,
          },
        ),
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });
    const firstSocket = MockWebSocket.instances[0];

    act(() => {
      firstSocket?.open();
    });
    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/^Hermes disconnected — reconnecting$/);
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();

    act(() => {
      firstSocket?.receive(
        JSON.stringify({
          event_id: "snapshot-4",
          sequence: 4,
          occurred_at: "2026-07-30T00:00:00Z",
          source: "test",
          evidence: "verified",
          type: "snapshot.replaced",
          payload: { snapshot: { ...bootstrap.world, connection: "connected" } },
        }),
      );
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Task for Yume")).toBeEnabled();

    act(() => {
      firstSocket?.disconnect();
    });
    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/^Hermes disconnected — reconnecting$/);
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(2);
    });
    const reconnectedSocket = MockWebSocket.instances[1];

    act(() => {
      reconnectedSocket?.open();
    });
    expect(screen.getByRole("status")).toHaveTextContent(/^Hermes disconnected — reconnecting$/);
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();

    act(() => {
      reconnectedSocket?.receive(
        JSON.stringify({
          event_id: "snapshot-4-reconnected",
          sequence: 4,
          occurred_at: "2026-07-30T00:00:01Z",
          source: "test",
          evidence: "verified",
          type: "snapshot.replaced",
          payload: { snapshot: { ...bootstrap.world, connection: "connected" } },
        }),
      );
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Task for Yume")).toBeEnabled();
  });

  it("keeps the office surface available when bootstrap fails", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByText("Hermes disconnected")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/bootstrap");
      expect(MockWebSocket.instances).toHaveLength(0);
    });
  });

  it("serializes rapid diagnostic retries and closes the retry socket on unmount", async () => {
    let bootstrapAttempts = 0;
    let resolveRetry: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (input === "/api/bootstrap") {
        bootstrapAttempts += 1;
        if (bootstrapAttempts === 1) {
          return Promise.reject(new TypeError("offline"));
        }
        return Promise.resolve(
          new Response(JSON.stringify(bootstrap), {
            headers: { "Content-Type": "application/json" },
            status: 200,
          }),
        );
      }
      if (input === "/api/diagnostics") {
        return Promise.resolve(
          new Response(
            JSON.stringify(
              bootstrapAttempts === 1
                ? {
                    status: "hermes_unavailable",
                    file: null,
                    message: "Hermes is starting",
                  }
                : { status: "ready", file: null, message: "" },
            ),
            {
              headers: { "Content-Type": "application/json" },
              status: 200,
            },
          ),
        );
      }
      if (input === "/api/diagnostics/retry") {
        return new Promise<Response>((resolve) => {
          resolveRetry = resolve;
        });
      }
      throw new Error(`Unexpected request: ${String(input)}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { unmount } = render(<App />);

    const retryButton = await screen.findByRole("button", { name: "Retry connection" });
    act(() => {
      fireEvent.click(retryButton);
      fireEvent.click(retryButton);
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(retryButton).toBeDisabled();
    expect(resolveRetry).toBeDefined();

    resolveRetry?.(
      new Response(JSON.stringify({ status: "ready", file: null, message: "" }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });
    const socket = MockWebSocket.instances[0];

    unmount();
    expect(socket?.close).toHaveBeenCalledOnce();
  });

  it("keeps raw world connection changes masked without socket synchronization", () => {
    useWorldStore.setState({
      agents: [yume, delegatedWorker],
      connection: "disconnected",
      telemetry_mode: "enhanced",
    });

    render(<App />);

    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByText("Yume is working")).toBeInTheDocument();
    expect(screen.getByText("Hermes disconnected")).toBeInTheDocument();
    expect(screen.getByText("2 agents")).toBeInTheDocument();
    expect(screen.getByText("Telemetry: enhanced")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/^Hermes disconnected — reconnecting$/);
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send task" })).toBeDisabled();

    act(() => {
      useWorldStore.setState({ connection: "connected" });
    });

    expect(screen.getByText("Hermes disconnected")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/^Hermes disconnected — reconnecting$/);
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();
  });

  it("submits a connected task through the dashboard API client", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      input === "/api/tasks"
        ? Promise.resolve(new Response(null, { status: 202 }))
        : Promise.resolve(
            new Response(
              JSON.stringify({
                ...bootstrap,
                world: { ...bootstrap.world, connection: "connected" },
              }),
              {
                headers: { "Content-Type": "application/json" },
                status: 200,
              },
            ),
          ),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket?.open();
      socket?.receive(
        JSON.stringify({
          event_id: "snapshot-4",
          sequence: 4,
          occurred_at: "2026-07-30T00:00:00Z",
          source: "test",
          evidence: "verified",
          type: "snapshot.replaced",
          payload: { snapshot: { ...bootstrap.world, connection: "connected" } },
        }),
      );
    });

    await user.type(screen.getByLabelText("Task for Yume"), "  Inspect Hermes  ");
    await user.click(screen.getByRole("button", { name: "Send task" }));

    expect(fetchMock).toHaveBeenCalledWith("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Inspect Hermes" }),
    });
  });

  it("renders one selected agent and clears selection from the close control", async () => {
    const user = userEvent.setup();
    useWorldStore.setState({
      agents: [yume, delegatedWorker],
      selectedAgentId: delegatedWorker.agent_id,
    });

    render(<App />);

    expect(
      screen.getByRole("complementary", { name: "Research worker details" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("complementary")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Close agent details" }));

    expect(useWorldStore.getState().selectedAgentId).toBeNull();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("clears a missing selection so a re-added agent does not reopen the inspector", () => {
    useWorldStore.setState({
      agents: [yume, delegatedWorker],
      selectedAgentId: delegatedWorker.agent_id,
    });

    render(<App />);
    expect(
      screen.getByRole("complementary", { name: "Research worker details" }),
    ).toBeInTheDocument();

    act(() => {
      useWorldStore.setState({ agents: [yume] });
    });

    expect(useWorldStore.getState().selectedAgentId).toBeNull();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();

    act(() => {
      useWorldStore.setState({ agents: [yume, delegatedWorker] });
    });

    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
