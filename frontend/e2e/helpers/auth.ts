import { expect, type Page } from "@playwright/test";

export async function loginAsAdmin(page: Page, targetPath = "/en/dashboard") {
  const isTargetUrl = (url: URL) => url.pathname === targetPath;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.goto(`/en/login?callbackUrl=${encodeURIComponent(targetPath)}`);
    await page.waitForLoadState("domcontentloaded");

    await expect(page.getByLabel("Username")).toBeEditable();
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password").fill("admin123");

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
