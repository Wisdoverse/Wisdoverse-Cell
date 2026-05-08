import { defineConfig, devices } from "@playwright/test";

const playwrightHost = "127.0.0.1";
const playwrightPort = process.env.PLAYWRIGHT_PORT ?? "3100";
const defaultBaseURL = `http://${playwrightHost}:${playwrightPort}`;
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? defaultBaseURL;
const workers = process.env.PLAYWRIGHT_WORKERS ? Number(process.env.PLAYWRIGHT_WORKERS) : 1;
const useExternalServer =
  process.env.PLAYWRIGHT_SKIP_WEB_SERVER === "1" || Boolean(process.env.PLAYWRIGHT_BASE_URL);

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
        command: `AUTH_SECRET=playwright-dev-secret ENABLE_DEV_AUTH=true DEV_AUTH_USERNAME=dev@itoy.ai DEV_AUTH_PASSWORD=itoy@2025 DEV_AUTH_ROLE=admin NEXTAUTH_URL=${defaultBaseURL} npm run dev -- --hostname ${playwrightHost} --port ${playwrightPort}`,
        url: baseURL,
        reuseExistingServer: false,
        timeout: 120_000,
      },
});
