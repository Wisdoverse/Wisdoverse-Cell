import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import path from "node:path";

const playwrightHost = "127.0.0.1";
const playwrightPort = process.env.PLAYWRIGHT_PORT ?? "3100";
const defaultBaseURL = `http://${playwrightHost}:${playwrightPort}`;
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? defaultBaseURL;
const workers = process.env.PLAYWRIGHT_WORKERS ? Number(process.env.PLAYWRIGHT_WORKERS) : 1;
const useExternalServer =
  process.env.PLAYWRIGHT_SKIP_WEB_SERVER === "1" || Boolean(process.env.PLAYWRIGHT_BASE_URL);
const adminStorePath =
  process.env.PLAYWRIGHT_ADMIN_STORE_PATH ??
  path.join(tmpdir(), `wisdoverse-cell-playwright-admin-${process.pid}-${Date.now()}.json`);

/**
 * Playwright configuration for E2E tests.
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers,
  reporter: "html",

  use: {
    baseURL,
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: useExternalServer
    ? undefined
    : {
        command: `AUTH_SECRET=playwright-dev-secret WEBUI_ADMIN_STORE_PATH=${adminStorePath} NEXTAUTH_URL=${defaultBaseURL} npm run dev -- --hostname ${playwrightHost} --port ${playwrightPort}`,
        url: baseURL,
        reuseExistingServer: false,
        timeout: 120_000,
      },
});
