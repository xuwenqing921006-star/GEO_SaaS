import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDir = fileURLToPath(new URL("..", import.meta.url));
const backendDir = path.resolve(frontendDir, "../backend");

export default defineConfig({
  testDir: ".",
  testMatch: "t011-p06-real.e2e.ts",
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:5180",
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
        "uv run uvicorn tests.e2e_server:app --app-dir . --host 127.0.0.1 --port 8001",
      cwd: backendDir,
      url: "http://127.0.0.1:8001/api/v1/health/live",
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --host 127.0.0.1 --port 5180",
      cwd: frontendDir,
      env: {
        VITE_USE_MOCK: "false",
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8001",
      },
      url: "http://127.0.0.1:5180",
      reuseExistingServer: false,
    },
  ],
});
