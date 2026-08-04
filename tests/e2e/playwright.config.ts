import { defineConfig, devices } from "@playwright/test";

const projectRoot = process.cwd();
const runIdentifier = `yume-e2e-${process.pid}`;

const dashboardEnvironment = {
  HERMES_API_KEY: "e2e",
  HERMES_BASE_URL: "http://127.0.0.1:8642",
  YUME_HOOK_TOKEN: "hook-secret",
  YUME_DASHBOARD_CONFIG: "config/dashboard.example.yaml",
  YUME_ASSET_PACK_ROOT: "asset-packs",
  YUME_WEB_DIST: "apps/web/dist",
  DATA_DIR: `/tmp/${runIdentifier}`,
  UV_CACHE_DIR: "/tmp/yume-e2e-uv-cache",
};

export default defineConfig({
  testDir: ".",
  // The test-only fixture selector changes Fake Hermes process state, so scenarios run serially.
  fullyParallel: false,
  timeout: 20_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "(cd apps/web && node_modules/.bin/tsc -b && node_modules/.bin/vite build) && tests/e2e/start-dashboard.sh",
      cwd: projectRoot,
      env: dashboardEnvironment,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "uv run --package yume-api uvicorn yume_api.main:app --host 127.0.0.1 --port 8001",
      cwd: projectRoot,
      env: {
        HERMES_API_KEY: "e2e",
        YUME_DASHBOARD_CONFIG: "config/dashboard.example.yaml",
        YUME_ASSET_PACK_ROOT: "tests/fake_hermes/invalid-assets",
        YUME_WEB_DIST: "apps/web/dist",
        DATA_DIR: `/tmp/${runIdentifier}-invalid-assets`,
        UV_CACHE_DIR: "/tmp/yume-e2e-uv-cache",
      },
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
