import { defineConfig, devices } from "@playwright/test";

/**
 * Mobile smoke tests at the iPhone 13 viewport, against a production build
 * using the deterministic mock coach (no API key needed).
 *
 *   npx playwright install webkit chromium   # once
 *   npm run test:e2e
 *
 * WebKit is the closest desktop proxy for iPhone Safari, but it is NOT a
 * substitute for testing on the physical device.
 */
const PORT = Number(process.env.E2E_PORT || 3100);

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "iphone13-webkit", use: { ...devices["iPhone 13"] } },
    { name: "iphone13-chromium", use: { ...devices["iPhone 13"], browserName: "chromium" } },
  ],
  webServer: {
    command: `npm run start -- -p ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    env: { COACH_MODE: "mock" },
    timeout: 120_000,
  },
});
