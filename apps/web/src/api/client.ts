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
