import { expect, type Page } from "@playwright/test";

export async function loginAsAdmin(page: Page, targetPath = "/en/dashboard") {
  const isTargetUrl = (url: URL) => url.pathname === targetPath;
  const username = process.env.DEV_AUTH_USERNAME;
  const password = process.env.DEV_AUTH_PASSWORD;
  if (!username || !password) {
    throw new Error("DEV_AUTH_USERNAME and DEV_AUTH_PASSWORD are required for e2e login.");
  }

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.goto(`/en/login?callbackUrl=${encodeURIComponent(targetPath)}`);
    await page.waitForLoadState("domcontentloaded");

    await expect(page.getByLabel("Username")).toBeEditable();
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill(password);

    await Promise.all([
      page.waitForURL(isTargetUrl, { timeout: 15_000 }).catch(() => undefined),
      page.getByRole("button", { name: /login/i }).click(),
    ]);

    if (isTargetUrl(new URL(page.url()))) {
      return;
    }
  }

  await expect(page).toHaveURL(isTargetUrl, { timeout: 15_000 });
}
