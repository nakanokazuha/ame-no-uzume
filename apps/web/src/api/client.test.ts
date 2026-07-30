import { afterEach, describe, expect, it, vi } from "vitest";
import { getBootstrap, retryDiagnostics, submitTask } from "./client";

describe("REST API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the bootstrap response", async () => {
    const payload = {
      world: { sequence: 0, connection: "starting", agents: [] },
      asset_pack: {
        id: "placeholder",
        map: "office.json",
        atlas: "office.png",
        anchors: {},
        animations: {},
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBootstrap()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/bootstrap");
  });

  it("submits text tasks as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(submitTask("Inspect the task")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Inspect the task" }),
    });
  });

  it("retries Hermes startup diagnostics", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ready", file: null, message: "" })),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(retryDiagnostics()).resolves.toEqual({ status: "ready", file: null, message: "" });
    expect(fetchMock).toHaveBeenCalledWith("/api/diagnostics/retry", { method: "POST" });
  });

  it("includes the endpoint, status, and response text in non-OK errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Hermes is unavailable", { status: 503 })),
    );

    await expect(getBootstrap()).rejects.toThrow(
      "GET /api/bootstrap failed (503): Hermes is unavailable",
    );
  });
});
