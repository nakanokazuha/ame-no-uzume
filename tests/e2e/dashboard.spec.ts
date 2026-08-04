import { expect, test, type Page } from "@playwright/test";
import startEnvelope from "../fake_hermes/fixtures/hook-start.json";

async function submitTask(page: Page, text: string): Promise<void> {
  await page.getByLabel("Task for Yume").fill(text);
  await page.getByRole("button", { name: "Send task" }).click();
}

async function selectScenario(
  request: import("@playwright/test").APIRequestContext,
  scenario: string,
): Promise<void> {
  const response = await request.post(`http://127.0.0.1:8642/__test/scenario/${scenario}`);
  await expect(response).toBeOK();
}

async function selectLobbyAgent(page: Page): Promise<void> {
  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) {
    throw new Error("Office canvas has no visible bounds");
  }

  const desiredZoom = Math.min(box.width / 768, box.height / 384);
  const zoom = [1, 1.5, 2].reduce((closest, level) =>
    Math.abs(level - desiredZoom) < Math.abs(closest - desiredZoom) ? level : closest,
  );
  const scrollX = Math.max(0, (768 - box.width / zoom) / 2);
  const scrollY = Math.max(0, (384 - box.height / zoom) / 2);
  await page.mouse.click(
    box.x + (544 - scrollX) * zoom,
    box.y + (208 - scrollY) * zoom,
  );
}

test("initial connection reports a connected idle Yume", async ({ page, request }) => {
  await selectScenario(request, "initial-connection");
  await page.goto("/?scenario=initial-connection");

  await expect(page.getByText("Hermes connected")).toBeVisible();
  await expect(page.getByText("Yume is idle")).toBeVisible();
});

test("enhanced telemetry shows verified role and goal", async ({ page, request }) => {
  await page.goto("http://127.0.0.1:8000");
  const ingestion = await request.post("http://127.0.0.1:8000/api/integrations/hermes/events", {
    headers: { Authorization: "Bearer hook-secret" },
    data: startEnvelope,
  });
  await expect(ingestion).toBeOK();

  await expect(page.getByText("Telemetry: enhanced")).toBeVisible();
  await expect(page.getByText("Researcher")).toBeVisible();
  await selectLobbyAgent(page);

  const inspector = page.getByRole("complementary", { name: "Researcher details" });
  await expect(inspector).toBeVisible();
  await expect(inspector.getByText("Delegated worker")).toBeVisible();
  await expect(inspector.getByText("Verified")).toBeVisible();
  await expect(inspector.getByText("Compare Hermes event hooks")).toBeVisible();
});

test("scheduled discovery adds the persistent automation worker", async ({ page, request }) => {
  await selectScenario(request, "initial-connection");
  await page.goto("/?scenario=scheduled-job");

  await expect(page.getByText("Daily memory")).toBeVisible();
});

test("text task streaming concatenates two assistant deltas", async ({ page, request }) => {
  await selectScenario(request, "streaming");
  await page.goto("/?scenario=streaming");
  await submitTask(page, "Stream a response");

  await expect(page.getByLabel("Streaming response")).toHaveText("First second final");
  await expect(page.getByText("First second final")).toBeVisible();
});

test("delegated worker enters, reports, and leaves", async ({ page, request }) => {
  await selectScenario(request, "delegated-task");
  await page.goto("/?scenario=delegated-task");
  await submitTask(page, "Research Hermes hooks");

  await expect(page.getByText("Delegated Worker")).toBeVisible();
  await expect(page.getByText("Research library")).toBeVisible();
  await expect(page.getByText("Hooks research complete")).toBeVisible();
  await expect(page.getByText("Delegated Worker")).not.toBeVisible();
  await expect(page.getByText("Yume is idle")).toBeVisible();
});

test("approval resolution clears the pending decision", async ({ page, request }) => {
  await selectScenario(request, "approval");
  await page.goto("/?scenario=approval");
  await submitTask(page, "Request approval");

  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible();
});

test("failed run reports the failure and returns Yume to idle", async ({ page, request }) => {
  await selectScenario(request, "failed-run");
  await page.goto("/?scenario=failed-run");
  await submitTask(page, "Fail this task");

  await expect(page.getByText("Task failed")).toBeVisible();
  await expect(page.getByText("Yume is idle")).toBeVisible();
});

test("forced reconnect receives a fresh snapshot", async ({ page, request }) => {
  await selectScenario(request, "reconnect-snapshot");
  const receivedSnapshots: unknown[] = [];
  page.on("websocket", (socket) => {
    socket.on("framereceived", (frame) => {
      try {
        const payload: unknown = JSON.parse(frame.payload);
        if (
          typeof payload === "object" &&
          payload !== null &&
          "type" in payload &&
          payload.type === "snapshot.replaced"
        ) {
          receivedSnapshots.push(payload);
        }
      } catch {
        // Ignore non-JSON WebSocket frames from unrelated browser tooling.
      }
    });
  });
  await page.goto("/?scenario=reconnect-snapshot");
  await expect(page.getByText("Hermes connected")).toBeVisible();
  await expect.poll(() => receivedSnapshots).toHaveLength(1);

  await page.context().setOffline(true);
  await expect(page.getByText("Hermes disconnected — reconnecting")).toBeVisible();
  await page.context().setOffline(false);

  await expect(page.getByText("Hermes connected")).toBeVisible();
  await expect.poll(() => receivedSnapshots.length).toBeGreaterThanOrEqual(2);
});

test("invalid assets reports the precise diagnostic", async ({ page }) => {
  await page.goto("http://127.0.0.1:8001/?scenario=invalid-assets");

  await expect(page.getByText("Asset pack needs attention")).toBeVisible();
  await expect(page.getByText("missing semantic anchors: ['lobby']")).toBeVisible();
  await expect(page.getByText("tests/fake_hermes/invalid-assets/placeholder/pack.json")).toBeVisible();
});

test("session reset replaces the active session used by the next task", async ({ page, request }) => {
  await selectScenario(request, "session-reset");
  await page.goto("/?scenario=session-reset");
  const bootstrap = await request.get("/api/bootstrap");
  await expect(bootstrap).toBeOK();
  const bootstrapBody = (await bootstrap.json()) as { world: { session_id: string } };
  const resetResponse = page.waitForResponse("**/api/session/reset");
  await page.getByRole("button", { name: "Reset conversation" }).click();
  const reset = await resetResponse;
  expect(reset.status()).toBe(200);
  const resetBody = (await reset.json()) as { session_id: string };
  expect(resetBody.session_id).not.toBe(bootstrapBody.world.session_id);
  await expect(page.getByText("Conversation reset")).toBeVisible();

  await submitTask(page, "Verify session reset");
  await expect(page.getByText("Session reset task complete")).toBeVisible();
  const lastStream = await request.get("http://127.0.0.1:8642/__test/last-stream-session");
  await expect(lastStream).toBeOK();
  await expect(await lastStream.json()).toEqual({ session_id: resetBody.session_id });
});
