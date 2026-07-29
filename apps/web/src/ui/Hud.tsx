import type { AgentView, WorldSnapshot } from "@yume/contracts";
import type { JSX } from "react";

export interface HudProps {
  yume: AgentView | undefined;
  connection: WorldSnapshot["connection"];
  agentCount: number;
  telemetryMode: NonNullable<WorldSnapshot["telemetry_mode"]>;
}

function humanizeStatus(status: AgentView["status"]): string {
  return status.replaceAll("_", " ");
}

export function Hud({
  yume,
  connection,
  agentCount,
  telemetryMode,
}: HudProps): JSX.Element {
  return (
    <header className="hud">
      <strong>YUME HQ</strong>
      <span>Yume is {yume ? humanizeStatus(yume.status) : "unavailable"}</span>
      <span>Hermes {connection}</span>
      <span>{agentCount} agents</span>
      <span>Telemetry: {telemetryMode}</span>
    </header>
  );
}
