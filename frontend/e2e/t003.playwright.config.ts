import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "t003-p02-p03.e2e.ts",
  fullyParallel: false,
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
  webServer: {
    command: "pnpm dev --host 127.0.0.1 --port 5174",
    env: { VITE_USE_MOCK: "true" },
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
});
