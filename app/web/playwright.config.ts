import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45000,
  // The dev server compiles a route on first use; assertions wait for that instead of failing at 5 s.
  expect: { timeout: 12000 },
  workers: 2,
  use: {
    ...devices["Pixel 5"],
    viewport: { width: 390, height: 844 },
    baseURL: "http://localhost:3000",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120000,
  },
});
