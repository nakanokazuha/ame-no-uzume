import { describe, expect, it } from "vitest";
import { findPath } from "./paths";

describe("findPath", () => {
  it("routes around blocked tiles", () => {
    const path = findPath(
      [
        [0, 0, 0],
        [0, 1, 0],
        [0, 0, 0],
      ],
      { x: 0, y: 1 },
      { x: 2, y: 1 },
    );

    expect(path).not.toContainEqual({ x: 1, y: 1 });
    expect(path.at(-1)).toEqual({ x: 2, y: 1 });
  });

  it("uses NE first when equivalent diagonal routes are available", () => {
    expect(
      findPath(
        [
          [0, 0, 0],
          [0, 0, 0],
          [0, 0, 0],
        ],
        { x: 1, y: 1 },
        { x: 2, y: 0 },
      ),
    ).toEqual([
      { x: 1, y: 1 },
      { x: 2, y: 0 },
    ]);
  });

  it("returns no path when the goal is unreachable", () => {
    expect(
      findPath(
        [
          [0, 1, 0],
          [1, 1, 1],
          [0, 1, 0],
        ],
        { x: 0, y: 0 },
        { x: 2, y: 2 },
      ),
    ).toEqual([]);
  });
});
