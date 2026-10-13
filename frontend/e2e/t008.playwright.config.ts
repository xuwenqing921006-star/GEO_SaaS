import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDir = fileURLToPath(new URL("..", import.meta.url));
const backendDir = path.resolve(frontendDir, "../backend");

export default defineConfig({
  testDir: ".",
  testMatch: "t008-p03-p04-real.e2e.ts",
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:5177",
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
        "uv run uvicorn tests.e2e_server:app --app-dir . --host 127.0.0.1 --port 8005",
      cwd: backendDir,
      url: "http://127.0.0.1:8005/api/v1/health/live",
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --host 127.0.0.1 --port 5177",
      cwd: frontendDir,
      env: {
        VITE_USE_MOCK: "false",
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8005",
      },
      url: "http://127.0.0.1:5177",
      reuseExistingServer: false,
    },
  ],
});
