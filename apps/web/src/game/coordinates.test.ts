import { describe, expect, it } from "vitest";
import { tileToWorld } from "./coordinates";

describe("tileToWorld", () => {
  it("projects isometric tile coordinates", () => {
    expect(tileToWorld(2, 1, 64, 32)).toEqual({ x: 32, y: 48 });
  });

  it("preserves negative horizontal offsets and rounds fractional tile dimensions", () => {
    expect(tileToWorld(1, 3, 63, 31)).toEqual({ x: -63, y: 62 });
  });
});
