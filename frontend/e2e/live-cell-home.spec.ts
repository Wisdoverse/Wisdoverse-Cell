import { test, expect } from "@playwright/test";

/**
 * Live verification spec — runs against any deployed Wisdoverse Cell web tier.
 * Hostname, credentials, and base URL are passed via env so the spec stays
 * deployment-agnostic and contributors can point it at their own instance.
 * Skipped by default; set `LIVE_CELL_HOME=1` to enable.
 *
 * Usage:
 *   PLAYWRIGHT_BASE_URL=https://<live-cell-host> \
 *   PLAYWRIGHT_SKIP_WEB_SERVER=1 \
 *   LIVE_CELL_HOME=1 \
 *   LIVE_USERNAME=<operator-username> \
 *   LIVE_PASSWORD=<operator-password> \
 *   npx playwright test e2e/live-cell-home.spec.ts
 *
 * Asserts: when no AgentRun is in flight, the home dashboard's
 * `Running` / `Errors` / `Need Attention` / `Pending Approvals` stat
 * cards all read `0`. Regression guard for the lifecycle-vs-runtime
 * status split documented in `docs/overview/architecture.md`.
 */

const enabled = process.env.LIVE_CELL_HOME === "1";

test.describe.configure({ timeout: 120_000 });

test.skip(!enabled, "Set LIVE_CELL_HOME=1 to run the live verification spec.");

test("home greeting reads Running=0 against live backend", async ({ page }) => {
  const username = process.env.LIVE_USERNAME ?? "";
  const password = process.env.LIVE_PASSWORD ?? "";
  test.skip(!username || !password, "Set LIVE_USERNAME and LIVE_PASSWORD.");

  await page.goto("/zh/login?callbackUrl=%2Fzh%2Fhome");
  await page.waitForLoadState("domcontentloaded");

  await page.getByLabel(/用户名|Username/i).fill(username);
  await page.getByLabel(/密码|Password/i).fill(password);

  await Promise.all([
    page.waitForURL(/\/zh\/home(\?|$)/, { timeout: 30_000 }),
    page.getByRole("button", { name: /登录|Login/i }).click(),
  ]);

  // Wait for SWR queries to settle and the StatCards to render.
  const statValue = (label: RegExp) =>
    page.locator("p", { hasText: label }).locator("..").locator("div.text-3xl").first();

  const running = statValue(/^(Running|运行中)$/);
  await expect(running).toBeVisible({ timeout: 30_000 });
  await expect(running).toHaveText("0");

  await expect(statValue(/^(Errors|异常)$/)).toHaveText("0");
  await expect(statValue(/^(Need Attention|待处理)$/)).toHaveText("0");
  await expect(statValue(/^(Pending Approvals|待审批)$/)).toHaveText("0");
});
