import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the office canvas and task control", () => {
    render(<App />);
    expect(screen.getByTestId("office-canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Task Yume" })).toBeInTheDocument();
  });
});
