import type { JSX } from "react";

export function App(): JSX.Element {
  return (
    <main>
      <div data-testid="office-canvas" />
      <button type="button">Task Yume</button>
    </main>
  );
}
