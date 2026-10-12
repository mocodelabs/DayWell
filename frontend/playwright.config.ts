import { defineConfig, devices } from "@playwright/test";

// End-to-end tests drive a real browser against the real Django API on a dedicated PostgreSQL database (daywell_e2e),
// flushed at start. Reminder dispatch uses the real pipeline via the test-alarm endpoint (no hour-long waits).
//   npm run e2e                                   # starts the backend (8021) and Vite (5194) itself
//   E2E_PYTHON=/path/to/python npm run e2e         # choose the interpreter
//   E2E_DATABASE_URL=postgres://... npm run e2e    # choose the database (it is FLUSHED)
const ci = !!process.env.CI;

export default defineConfig({
  testDir: "e2e",
  testMatch: ["**/*.e2e.ts"],
  fullyParallel: false,
  workers: 1,
  retries: ci ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: ci ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: { baseURL: "http://127.0.0.1:5194", trace: "retain-on-failure", screenshot: "only-on-failure", timezoneId: "Africa/Nairobi" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: ["**/mobile.e2e.ts"] },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: ["**/mobile.e2e.ts"] },
  ],
  webServer: [
    { command: "node e2e/start-backend.mjs", url: "http://127.0.0.1:8021/health/live/", reuseExistingServer: !ci, timeout: 240_000, stdout: "pipe", stderr: "pipe" },
    { command: "npm run dev -- --port 5194 --strictPort --host 127.0.0.1", url: "http://127.0.0.1:5194", reuseExistingServer: !ci, timeout: 120_000,
      env: { VITE_PROXY_TARGET: "http://127.0.0.1:8021" } },
  ],
});
