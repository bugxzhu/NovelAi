import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false, // shared SQLite
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3300",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "cd .. && source .venv/bin/activate && uvicorn app.main:app --port 8005",
      url: "http://127.0.0.1:8005/api/health",
      timeout: 30_000,
      reuseExistingServer: true,
    },
    {
      command: "npm run dev",
      url: "http://localhost:3300",
      timeout: 60_000,
      reuseExistingServer: true,
    },
  ],
});
