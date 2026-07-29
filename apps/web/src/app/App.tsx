import { useEffect, useState, type JSX } from "react";
import { useStore } from "zustand";
import type { WorldSnapshot } from "@yume/contracts";
import { getBootstrap, submitTask, type BootstrapResponse } from "../api/client";
import { connectWorldSocket } from "../api/socket";
import { OfficeGame } from "../game/OfficeGame";
import { useWorldStore } from "../store/world";
import { AgentInspector } from "../ui/AgentInspector";
import { ChatPanel } from "../ui/ChatPanel";
import { ConnectionOverlay } from "../ui/ConnectionOverlay";
import { Hud } from "../ui/Hud";

function clearSelectedAgent(): void {
  useWorldStore.getState().selectAgent(null);
}

function hydrateWorld(snapshot: WorldSnapshot): void {
  useWorldStore.setState({
    sequence: snapshot.sequence,
    connection: snapshot.connection,
    telemetry_mode: snapshot.telemetry_mode ?? "standard",
    session_id: snapshot.session_id ?? null,
    agents: snapshot.agents,
    conversation: snapshot.conversation ?? [],
    streamingText: "",
    streamingMessageId: null,
  });
}

function worldSocketUrl(): string {
  const url = new URL("/api/events", window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function App(): JSX.Element {
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [isSocketSynchronized, setSocketSynchronized] = useState(false);
  const agents = useStore(useWorldStore, (state) => state.agents);
  const connection = useStore(useWorldStore, (state) => state.connection);
  const conversation = useStore(useWorldStore, (state) => state.conversation);
  const streamingText = useStore(useWorldStore, (state) => state.streamingText);
  const telemetryMode = useStore(useWorldStore, (state) => state.telemetry_mode);
  const selectedAgentId = useStore(useWorldStore, (state) => state.selectedAgentId);
  const yume = agents.find((agent) => agent.kind === "yume");
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId);
  const visibleConnection = isSocketSynchronized ? connection : "disconnected";

  useEffect(() => {
    if (selectedAgentId !== null && selectedAgent === undefined) {
      clearSelectedAgent();
    }
  }, [selectedAgent, selectedAgentId]);

  useEffect(() => {
    let cancelled = false;
    let disconnectWorldSocket: (() => void) | undefined;

    const initialize = async (): Promise<void> => {
      try {
        const response = await getBootstrap();
        if (cancelled) {
          return;
        }

        hydrateWorld(response.world);
        setBootstrap(response);
        disconnectWorldSocket = connectWorldSocket(
          worldSocketUrl(),
          (event) => {
            const previousSequence = useWorldStore.getState().sequence;
            useWorldStore.getState().applyEvent(event);

            const resynchronized =
              event.type === "snapshot.replaced"
                ? event.sequence >= previousSequence
                : event.sequence > previousSequence;
            if (!cancelled && resynchronized) {
              setSocketSynchronized(true);
            }
          },
          (transportOpen) => {
            if (!cancelled && !transportOpen) {
              setSocketSynchronized(false);
            }
          },
        );
      } catch {
        // Task 11 owns diagnostics and retry UI. The office surface remains usable here.
      }
    };

    void initialize();

    return () => {
      cancelled = true;
      disconnectWorldSocket?.();
    };
  }, []);

  return (
    <main className="app">
      {bootstrap ? (
        <OfficeGame bootstrap={bootstrap} store={useWorldStore} />
      ) : (
        <div
          aria-label="Yume office loading"
          className="office"
          data-testid="office-canvas"
        />
      )}
      <Hud
        agentCount={agents.length}
        connection={visibleConnection}
        telemetryMode={telemetryMode}
        yume={yume}
      />
      <ConnectionOverlay connection={visibleConnection} />
      {selectedAgent && (
        <AgentInspector agent={selectedAgent} onClose={clearSelectedAgent} />
      )}
      <ChatPanel
        disabled={visibleConnection !== "connected"}
        onSubmit={submitTask}
        streamingText={streamingText}
        transcript={conversation.map((message) => (
          <p key={message.message_id}>
            <strong>{message.role === "user" ? "You" : "Yume"}:</strong>{" "}
            {message.text}
          </p>
        ))}
      />
    </main>
  );
}
