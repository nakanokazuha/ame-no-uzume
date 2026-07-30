import type { WorldSnapshot } from "@yume/contracts";

export type BootstrapResponse = {
  world: WorldSnapshot;
  asset_pack: {
    id: string;
    map: string;
    atlas: string;
    anchors: Record<string, { x: number; y: number }>;
    animations: Record<string, number[]>;
    ui?: {
      image: string;
      atlas: string;
      nine_slice: Record<string, [number, number, number, number]>;
    };
  };
};

export type DiagnosticResponse = {
  status: "ready" | "invalid_config" | "invalid_assets" | "hermes_unavailable";
  file: string | null;
  message: string;
};

async function responseError(response: Response, method: string, path: string): Promise<Error> {
  const body = (await response.text()).trim();
  const detail = body || response.statusText || "No response detail";
  return new Error(`${method} ${path} failed (${response.status}): ${detail}`);
}

export async function getBootstrap(): Promise<BootstrapResponse> {
  const response = await fetch("/api/bootstrap");
  if (!response.ok) {
    throw await responseError(response, "GET", "/api/bootstrap");
  }
  return (await response.json()) as BootstrapResponse;
}

export async function getDiagnostics(): Promise<DiagnosticResponse> {
  const response = await fetch("/api/diagnostics");
  if (!response.ok) {
    throw await responseError(response, "GET", "/api/diagnostics");
  }
  return (await response.json()) as DiagnosticResponse;
}

export async function retryDiagnostics(): Promise<DiagnosticResponse> {
  const response = await fetch("/api/diagnostics/retry", { method: "POST" });
  if (!response.ok) {
    throw await responseError(response, "POST", "/api/diagnostics/retry");
  }
  return (await response.json()) as DiagnosticResponse;
}

export async function submitTask(text: string): Promise<void> {
  const response = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw await responseError(response, "POST", "/api/tasks");
  }
}
