import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "t004-p04-p05.e2e.ts",
  use: { baseURL: "http://127.0.0.1:5175" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm dev --host 127.0.0.1 --port 5175",
    env: { VITE_USE_MOCK: "true" },
    url: "http://127.0.0.1:5175",
    reuseExistingServer: false,
  },
});
