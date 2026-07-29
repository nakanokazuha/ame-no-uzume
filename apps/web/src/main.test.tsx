import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./game/OfficeGame", () => ({
  OfficeGame: () => <div className="office" data-testid="office-canvas" />,
}));

describe("application entrypoint", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.resetModules();
  });

  it("explains when the application root is missing", async () => {
    await expect(import("./main")).rejects.toThrow(
      "Cannot mount Yume: missing #root element.",
    );
  });
});
