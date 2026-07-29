import type { WorldSnapshot } from "@yume/contracts";
import type { JSX } from "react";

export interface ConnectionOverlayProps {
  connection: WorldSnapshot["connection"];
}

export function ConnectionOverlay({
  connection,
}: ConnectionOverlayProps): JSX.Element | null {
  if (connection === "connected") {
    return null;
  }

  return (
    <div aria-atomic="true" aria-live="polite" role="status">
      Hermes disconnected — reconnecting
    </div>
  );
}
