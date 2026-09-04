import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry"
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "cd ../backend && ${PYTHON_BIN:-.venv/bin/python} -m uvicorn --app-dir src tests.api.e2e_server:app --host 127.0.0.1 --port 8000 --log-level warning",
      url: "http://127.0.0.1:8000/openapi.json",
      reuseExistingServer: false
    },
    {
      command: "vite --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false
    }
  ]
});
