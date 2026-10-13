import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDir = fileURLToPath(new URL("..", import.meta.url));
const backendDir = path.resolve(frontendDir, "../backend");

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.e2e.ts",
  testIgnore: [
    "t003-p02-p03.e2e.ts",
    "t004-p04-p05.e2e.ts",
    "t005-p06-p08.e2e.ts",
    "t013-production-smoke.e2e.ts",
    "t016-ui-refresh.e2e.ts",
  ],
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "uv run uvicorn tests.e2e_server:app --app-dir . --host 127.0.0.1 --port 8003",
      cwd: backendDir,
      url: "http://127.0.0.1:8003/api/v1/health/live",
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --host 127.0.0.1 --port 5174 --strictPort",
      cwd: frontendDir,
      env: {
        VITE_USE_MOCK: "false",
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8003",
      },
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
  ],
});
