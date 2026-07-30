import { useEffect, useRef, useState, type JSX } from "react";
import { useStore } from "zustand";
import type { WorldSnapshot } from "@yume/contracts";
import {
  getBootstrap,
  getDiagnostics,
  resetSession,
  resolveApproval,
  retryDiagnostics,
  submitTask,
  type BootstrapResponse,
  type DiagnosticResponse,
} from "../api/client";
import { connectWorldSocket } from "../api/socket";
import { OfficeGame } from "../game/OfficeGame";
import { useWorldStore } from "../store/world";
import { AgentInspector } from "../ui/AgentInspector";
import { ChatPanel } from "../ui/ChatPanel";
import { ConnectionOverlay } from "../ui/ConnectionOverlay";
import { DiagnosticOverlay } from "../ui/DiagnosticOverlay";
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
  const [diagnostic, setDiagnostic] = useState<DiagnosticResponse | null>(null);
  const [isRetryPending, setRetryPending] = useState(false);
  const [isSocketSynchronized, setSocketSynchronized] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<{
    runId: string;
    approvalId: string;
    prompt: string;
  } | null>(null);
  const [sessionResetNotice, setSessionResetNotice] = useState(false);
  const [lastRunFailure, setLastRunFailure] = useState<string | null>(null);
  const retryInitialization = useRef<() => void>(() => undefined);
  const isRetryInFlight = useRef(false);
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
    let initializationGeneration = 0;
    let disconnectWorldSocket: (() => void) | undefined;

    const initialize = async (): Promise<void> => {
      if (cancelled) {
        return;
      }
      const generation = ++initializationGeneration;
      disconnectWorldSocket?.();
      disconnectWorldSocket = undefined;
      setSocketSynchronized(false);
      try {
        const response = await getBootstrap();
        if (cancelled || generation !== initializationGeneration) {
          return;
        }

        hydrateWorld(response.world);
        setBootstrap(response);
        try {
          const nextDiagnostic = await getDiagnostics();
          if (!cancelled && generation === initializationGeneration) {
            setDiagnostic(nextDiagnostic);
          }
        } catch {
          // The operational scene remains usable if only diagnostics are unavailable.
        }
        if (cancelled || generation !== initializationGeneration) {
          return;
        }
        const disconnectSocket = connectWorldSocket(
          worldSocketUrl(),
          (event) => {
            const previousSequence = useWorldStore.getState().sequence;
            useWorldStore.getState().applyEvent(event);
            if (event.type === "approval.requested") {
              setPendingApproval({
                runId: event.payload.run_id,
                approvalId: event.payload.approval_id,
                prompt: event.payload.prompt,
              });
            }
            if (event.type === "run.finished" && event.payload.outcome === "failed") {
              setLastRunFailure(event.payload.error ?? "Task failed");
            }

            const resynchronized =
              event.type === "snapshot.replaced"
                ? event.sequence >= previousSequence
                : event.sequence > previousSequence;
            if (!cancelled && generation === initializationGeneration && resynchronized) {
              setSocketSynchronized(true);
            }
          },
          (transportOpen) => {
            if (!cancelled && generation === initializationGeneration && !transportOpen) {
              setSocketSynchronized(false);
            }
          },
        );
        if (cancelled || generation !== initializationGeneration) {
          disconnectSocket();
          return;
        }
        disconnectWorldSocket = disconnectSocket;
      } catch {
        try {
          const nextDiagnostic = await getDiagnostics();
          if (!cancelled && generation === initializationGeneration) {
            setDiagnostic(nextDiagnostic);
          }
        } catch {
          // Keep the office surface available when neither startup endpoint is reachable.
        }
      }
    };

    retryInitialization.current = () => {
      if (cancelled || isRetryInFlight.current) {
        return;
      }
      isRetryInFlight.current = true;
      setRetryPending(true);
      void (async () => {
        try {
          await retryDiagnostics();
          if (!cancelled) {
            await initialize();
          }
        } catch {
          if (!cancelled) {
            await initialize();
          }
        } finally {
          isRetryInFlight.current = false;
          if (!cancelled) {
            setRetryPending(false);
          }
        }
      })();
    };
    void initialize();

    const handleOffline = (): void => {
      disconnectWorldSocket?.();
      disconnectWorldSocket = undefined;
      setSocketSynchronized(false);
    };
    const handleOnline = (): void => {
      void initialize();
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    return () => {
      cancelled = true;
      initializationGeneration += 1;
      retryInitialization.current = () => undefined;
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      disconnectWorldSocket?.();
    };
  }, []);

  const resetConversation = async (): Promise<void> => {
    await resetSession();
    setSessionResetNotice(true);
  };

  const decideApproval = async (approved: boolean): Promise<void> => {
    if (pendingApproval === null) {
      return;
    }
    await resolveApproval(pendingApproval.runId, pendingApproval.approvalId, approved);
    setPendingApproval(null);
  };

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
      {diagnostic && (
        <DiagnosticOverlay
          diagnostic={diagnostic}
          isRetryPending={isRetryPending}
          retry={retryInitialization.current}
        />
      )}
      {selectedAgent && (
        <AgentInspector agent={selectedAgent} onClose={clearSelectedAgent} />
      )}
      <section aria-label="World activity" className="world-activity">
        {agents.map((agent) => (
          <p key={agent.agent_id}>
            <strong>{agent.display_name}</strong>
            {agent.task_summary ? ` — ${agent.task_summary}` : ""}
          </p>
        ))}
        {lastRunFailure && <p>{lastRunFailure}</p>}
        {sessionResetNotice && <p>Conversation reset</p>}
      </section>
      {pendingApproval && (
        <section aria-label="Approval required" className="approval-controls">
          <p>{pendingApproval.prompt}</p>
          <button onClick={() => void decideApproval(true)} type="button">
            Approve
          </button>
          <button onClick={() => void decideApproval(false)} type="button">
            Deny
          </button>
        </section>
      )}
      <ChatPanel
        disabled={visibleConnection !== "connected"}
        onReset={resetConversation}
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
