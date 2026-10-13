import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDir = fileURLToPath(new URL("..", import.meta.url));
const backendDir = path.resolve(frontendDir, "../backend");

export default defineConfig({
  testDir: ".",
  testMatch: "t012-p07-p08-real.e2e.ts",
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:5181",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 980 },
      },
    },
  ],
  webServer: [
    {
      command:
        "uv run uvicorn tests.e2e_server:app --app-dir . --host 127.0.0.1 --port 8002",
      cwd: backendDir,
      url: "http://127.0.0.1:8002/api/v1/health/live",
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --host 127.0.0.1 --port 5181",
      cwd: frontendDir,
      env: {
        VITE_USE_MOCK: "false",
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8002",
      },
      url: "http://127.0.0.1:5181",
      reuseExistingServer: false,
    },
  ],
});
