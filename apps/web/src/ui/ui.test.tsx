import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AgentView } from "@yume/contracts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/App";
import { useWorldStore } from "../store/world";
import { AgentInspector } from "./AgentInspector";
import { ChatPanel } from "./ChatPanel";

vi.mock("../game/OfficeGame", () => ({
  OfficeGame: () => <div className="office" data-testid="office-canvas" />,
}));

const panelStorageKey = "yume.task-panel.v1";
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
  started_at: "2026-07-29T00:00:00Z",
  status: "working",
  task_summary: "Research Hermes",
};

const scheduledWorker: AgentView = {
  agent_id: "scheduled-1",
  display_name: "Morning review",
  evidence: "verified",
  kind: "scheduled",
  next_run_at: "2026-07-30T00:00:00Z",
  room: "automation",
  started_at: null,
  status: "waiting_approval",
  task_summary: "Review overnight activity",
};

function createMemoryStorage(): Storage {
  const values = new Map<string, string>();

  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

function setViewport(width: number, height: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
}

beforeEach(() => {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: createMemoryStorage(),
  });
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  useWorldStore.setState(initialWorldState, true);
  setViewport(initialViewport.width, initialViewport.height);
  vi.useRealTimers();
});

describe("floating task UI", () => {
  it("submits a trimmed task and clears the input", async () => {
    const onSubmit = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(<ChatPanel onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Task for Yume"), "  Research Hermes  ");
    await user.click(screen.getByRole("button", { name: "Send task" }));

    expect(onSubmit).toHaveBeenCalledWith("Research Hermes");
    await waitFor(() => {
      expect(screen.getByLabelText("Task for Yume")).toHaveValue("");
    });
  });

  it("retains task text when submission is rejected", async () => {
    const onSubmit = vi.fn(async () => {
      throw new Error("Hermes rejected the task");
    });
    const user = userEvent.setup();

    render(<ChatPanel onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Task for Yume"), "Inspect Hermes");
    await user.click(screen.getByRole("button", { name: "Send task" }));

    expect(onSubmit).toHaveBeenCalledWith("Inspect Hermes");
    await waitFor(() => {
      expect(screen.getByLabelText("Task for Yume")).toHaveValue("Inspect Hermes");
    });
  });

  it("prevents a second submission while the first is pending", async () => {
    let resolveSubmission: (() => void) | undefined;
    const pendingSubmission = new Promise<void>((resolve) => {
      resolveSubmission = resolve;
    });
    const onSubmit = vi.fn(() => pendingSubmission);
    const user = userEvent.setup();

    render(<ChatPanel onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Task for Yume"), "Inspect Hermes");
    await user.click(screen.getByRole("button", { name: "Send task" }));
    const form = screen.getByRole("button", { name: "Send task" }).closest("form");
    const completeSubmission = resolveSubmission;
    if (!form || !completeSubmission) {
      throw new Error("Pending task submission form is missing");
    }
    fireEvent.submit(form);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send task" })).toBeDisabled();

    await act(async () => {
      completeSubmission();
      await pendingSubmission;
    });
  });

  it("does not submit a task containing only whitespace", async () => {
    const onSubmit = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(<ChatPanel onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Task for Yume"), "   ");
    const form = screen.getByRole("button", { name: "Send task" }).closest("form");
    if (!form) {
      throw new Error("Task submission form is missing");
    }
    fireEvent.submit(form);

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("presents transcript and streaming output in the live conversation region", () => {
    render(
      <ChatPanel
        onSubmit={async () => undefined}
        streamingText="Live Hermes response"
        transcript="Completed Hermes response"
      />,
    );

    const transcript = screen.getByText("Completed Hermes response");
    expect(transcript).toBeInTheDocument();
    expect(screen.getByText("Live Hermes response")).toBeInTheDocument();
    expect(transcript).toHaveAttribute("aria-live", "polite");
  });

  it("shows evidence and room for the selected sprite", () => {
    render(<AgentInspector agent={delegatedWorker} onClose={() => undefined} />);

    expect(screen.getByRole("complementary", { name: "Research worker details" })).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Research library")).toBeInTheDocument();
    expect(screen.getByText("Delegated worker")).toBeInTheDocument();
  });

  it("updates elapsed activity from the selected agent start time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-29T00:01:01Z"));

    render(<AgentInspector agent={delegatedWorker} onClose={() => undefined} />);

    expect(screen.getByText("Elapsed")).toBeInTheDocument();
    expect(screen.getByText("1m 1s")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1_000);
    });

    expect(screen.queryByText("1m 1s")).not.toBeInTheDocument();
    expect(screen.getByText("1m 2s")).toBeInTheDocument();
  });

  it("cleans up its elapsed display timer when the inspector closes", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-29T00:01:01Z"));
    const clearInterval = vi.spyOn(window, "clearInterval");

    const { unmount } = render(
      <AgentInspector agent={delegatedWorker} onClose={() => undefined} />,
    );
    unmount();

    expect(clearInterval).toHaveBeenCalledTimes(1);
  });

  it.each([
    {
      agent: { ...delegatedWorker, started_at: null },
      expected: "Not available",
      label: "missing",
    },
    {
      agent: { ...delegatedWorker, started_at: "not-a-date" },
      expected: "Unknown",
      label: "invalid",
    },
    {
      agent: { ...delegatedWorker, started_at: "2026-07-29T00:02:00Z" },
      expected: "Not started",
      label: "future",
    },
  ])("handles a $label start time honestly", ({ agent, expected }) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-29T00:01:01Z"));

    render(<AgentInspector agent={agent} onClose={() => undefined} />);

    expect(screen.getByText("Elapsed")).toBeInTheDocument();
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("shows verified task and next-run details for a scheduled worker", () => {
    render(<AgentInspector agent={scheduledWorker} onClose={() => undefined} />);

    expect(screen.getByText("Scheduled worker")).toBeInTheDocument();
    expect(screen.getByText("Automation bay")).toBeInTheDocument();
    expect(screen.getByText("waiting approval")).toBeInTheDocument();
    expect(screen.getByText("Review overnight activity")).toBeInTheDocument();
    const nextRun = document.querySelector("time");
    expect(nextRun).toHaveAttribute("datetime", "2026-07-30T00:00:00Z");
    expect(nextRun).not.toHaveTextContent("");
  });

  it("does not present an unverified task summary as observed detail", () => {
    render(
      <AgentInspector
        agent={{
          ...delegatedWorker,
          evidence: "inferred",
          task_summary: "Unverified specific task",
        }}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("Inferred")).toBeInTheDocument();
    expect(screen.queryByText("Unverified specific task")).not.toBeInTheDocument();
  });

  it("uses the CEO role and room labels for Yume", () => {
    render(<AgentInspector agent={yume} onClose={() => undefined} />);

    expect(screen.getByText("CEO")).toBeInTheDocument();
    expect(screen.getByText("CEO office")).toBeInTheDocument();
  });

  it("keeps the office visible and blocks task submission while Hermes is disconnected", () => {
    useWorldStore.setState({
      agents: [yume],
      connection: "disconnected",
      telemetry_mode: "standard",
    });

    render(<App />);

    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Hermes disconnected — reconnecting");
    expect(screen.getByLabelText("Task for Yume")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send task" })).toBeDisabled();
  });

  it("persists only panel presentation when the task panel is collapsed", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);

    render(
      <ChatPanel
        onSubmit={onSubmit}
        transcript="Hermes output must stay out of local storage"
      />,
    );

    await user.type(screen.getByLabelText("Task for Yume"), "Private task text");
    await user.click(screen.getByRole("button", { name: "Collapse task panel" }));

    expect(screen.queryByLabelText("Task for Yume")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send task" })).not.toBeInTheDocument();
    expect(screen.queryByText("Hermes output must stay out of local storage")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand task panel" })).toBeInTheDocument();

    const storageEntries = Array.from({ length: window.localStorage.length }, (_, index) => {
      const key = window.localStorage.key(index);
      return [key, key === null ? null : window.localStorage.getItem(key)] as const;
    });
    expect(storageEntries.map(([key]) => key)).toEqual([panelStorageKey]);
    const storageContents = storageEntries
      .flatMap(([key, value]) => [key, value])
      .filter((entry): entry is string => entry !== null)
      .join("\n");
    expect(storageContents).not.toContain("Private task text");
    expect(storageContents).not.toContain("Hermes output must stay out of local storage");

    const stored = window.localStorage.getItem(panelStorageKey);
    expect(stored).not.toBeNull();
    const storedPanel: Record<string, unknown> = JSON.parse(stored ?? "{}");
    expect(Object.keys(storedPanel).sort()).toEqual(["collapsed", "height", "width", "x", "y"]);
    expect(storedPanel).toEqual({
      x: expect.any(Number),
      y: expect.any(Number),
      width: expect.any(Number),
      height: expect.any(Number),
      collapsed: true,
    });

    await user.click(screen.getByRole("button", { name: "Expand task panel" }));
    const taskInput = screen.getByLabelText("Task for Yume");
    expect(taskInput).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send task" })).toBeEnabled();
    expect(screen.getByText("Hermes output must stay out of local storage")).toBeInTheDocument();
    await user.clear(taskInput);
    await user.type(taskInput, "Restored task");
    await user.click(screen.getByRole("button", { name: "Send task" }));
    expect(onSubmit).toHaveBeenCalledWith("Restored task");
  });

  it("restores a valid collapsed task-panel presentation", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      panelStorageKey,
      JSON.stringify({ x: 73, y: 121, width: 587, height: 463, collapsed: true }),
    );

    render(<ChatPanel onSubmit={async () => undefined} />);

    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "73px",
      top: "121px",
      width: "587px",
      height: "auto",
    });
    expect(screen.queryByLabelText("Task for Yume")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand task panel" }));
    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "73px",
      top: "121px",
      width: "587px",
      height: "463px",
    });
  });

  it("collapses to its header and restores saved geometry in a narrow viewport", async () => {
    const user = userEvent.setup();
    setViewport(320, 260);
    window.localStorage.setItem(
      panelStorageKey,
      JSON.stringify({ x: 0, y: 0, width: 320, height: 260, collapsed: true }),
    );

    render(<ChatPanel onSubmit={async () => undefined} />);

    const panel = screen.getByRole("region", { name: "Task Yume" });
    expect(panel).toHaveStyle({
      height: "auto",
      left: "0px",
      top: "0px",
      width: "320px",
    });

    await user.click(screen.getByRole("button", { name: "Expand task panel" }));

    expect(panel).toHaveStyle({
      height: "260px",
      left: "0px",
      top: "0px",
      width: "320px",
    });
  });

  it("moves and resizes the task panel with accessible controls", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      panelStorageKey,
      JSON.stringify({ x: 73, y: 121, width: 587, height: 463, collapsed: false }),
    );

    render(<ChatPanel onSubmit={async () => undefined} />);

    await user.click(screen.getByRole("button", { name: "Move task panel right" }));
    await user.click(screen.getByRole("button", { name: "Move task panel down" }));
    await user.click(screen.getByRole("button", { name: "Increase task panel size" }));

    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "97px",
      top: "145px",
      width: "627px",
      height: "503px",
    });
    expect(JSON.parse(window.localStorage.getItem(panelStorageKey) ?? "{}")).toEqual({
      x: 97,
      y: 145,
      width: 627,
      height: 503,
      collapsed: false,
    });
  });

  it("clamps movement and size controls to the panel bounds", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      panelStorageKey,
      JSON.stringify({ x: 0, y: 0, width: 720, height: 720, collapsed: false }),
    );

    render(<ChatPanel onSubmit={async () => undefined} />);

    await user.click(screen.getByRole("button", { name: "Move task panel left" }));
    await user.click(screen.getByRole("button", { name: "Move task panel up" }));
    await user.click(screen.getByRole("button", { name: "Increase task panel size" }));

    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "0px",
      top: "0px",
      width: "720px",
      height: "720px",
    });
  });

  it("falls back to an expanded panel when saved presentation data is invalid", () => {
    window.localStorage.setItem(
      panelStorageKey,
      JSON.stringify({ collapsed: true, width: "wide" }),
    );

    render(<ChatPanel onSubmit={async () => undefined} />);

    expect(screen.getByLabelText("Task for Yume")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse task panel" })).toBeInTheDocument();
  });

  it("fits the default task panel inside a narrow initial viewport", () => {
    setViewport(320, 260);

    render(<ChatPanel onSubmit={async () => undefined} />);

    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "0px",
      top: "0px",
      width: "320px",
      height: "260px",
    });
    expect(screen.getByRole("button", { name: "Collapse task panel" })).toBeInTheDocument();
  });

  it("re-clamps an open task panel when the viewport shrinks", () => {
    setViewport(1_000, 800);
    render(<ChatPanel onSubmit={async () => undefined} />);

    setViewport(300, 240);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });

    expect(screen.getByRole("region", { name: "Task Yume" })).toHaveStyle({
      left: "0px",
      top: "0px",
      width: "300px",
      height: "240px",
    });
    expect(screen.getByRole("button", { name: "Collapse task panel" })).toBeInTheDocument();
  });

  it("removes its viewport resize listener when unmounted", () => {
    const removeEventListener = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<ChatPanel onSubmit={async () => undefined} />);

    unmount();

    expect(removeEventListener).toHaveBeenCalledWith("resize", expect.any(Function));
  });
});
