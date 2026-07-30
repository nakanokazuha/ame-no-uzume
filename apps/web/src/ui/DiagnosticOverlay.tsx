import type { JSX } from "react";
import type { DiagnosticResponse } from "../api/client";

const diagnosticTitle: Record<DiagnosticResponse["status"], string> = {
  ready: "",
  invalid_config: "Configuration needs attention",
  invalid_assets: "Asset pack needs attention",
  hermes_unavailable: "Hermes unavailable",
};

export interface DiagnosticOverlayProps {
  diagnostic: DiagnosticResponse;
  isRetryPending: boolean;
  retry: () => void;
}

export function DiagnosticOverlay({
  diagnostic,
  isRetryPending,
  retry,
}: DiagnosticOverlayProps): JSX.Element | null {
  if (diagnostic.status === "ready") {
    return null;
  }

  return (
    <section aria-live="assertive" className="diagnostic-overlay" role="alert">
      <h1>{diagnosticTitle[diagnostic.status]}</h1>
      {diagnostic.file && <code>{diagnostic.file}</code>}
      <p>{diagnostic.message}</p>
      {diagnostic.status === "hermes_unavailable" && (
        <button disabled={isRetryPending} onClick={retry} type="button">
          Retry connection
        </button>
      )}
    </section>
  );
}
