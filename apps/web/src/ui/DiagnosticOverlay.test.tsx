import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiagnosticOverlay } from "./DiagnosticOverlay";

afterEach(cleanup);

describe("DiagnosticOverlay", () => {
  it("keeps the office unobstructed when the server is ready", () => {
    render(
      <DiagnosticOverlay
        diagnostic={{ status: "ready", file: null, message: "" }}
        isRetryPending={false}
        retry={vi.fn()}
      />,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("explains an unavailable Hermes connection and retries it on request", () => {
    const retry = vi.fn(async () => undefined);
    render(
      <DiagnosticOverlay
        diagnostic={{
          status: "hermes_unavailable",
          file: null,
          message: "Hermes connection failed (ConnectError); verify the local API server.",
        }}
        isRetryPending={false}
        retry={retry}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Hermes unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent(
      /Hermes connection failed \(ConnectError\)/,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("identifies an invalid asset file without offering a Hermes retry", () => {
    render(
      <DiagnosticOverlay
        diagnostic={{
          status: "invalid_assets",
          file: "asset-packs/custom/pack.json",
          message: "missing semantic anchors: ['lobby']",
        }}
        isRetryPending={false}
        retry={vi.fn()}
      />,
    );

    expect(screen.getByText("Asset pack needs attention")).toBeInTheDocument();
    expect(screen.getByText("asset-packs/custom/pack.json")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry connection" })).not.toBeInTheDocument();
  });
});
