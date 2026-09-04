import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry"
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "cd .. && .venv/bin/python -m tests.e2e_server",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false
    },
    {
      command: "vite --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false
    }
  ]
});
