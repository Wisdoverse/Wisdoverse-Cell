import { expect, type Page } from "@playwright/test";

const username = process.env.E2E_ADMIN_USERNAME ?? "e2e-admin@example.com";
const password = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password";

export async function loginAsAdmin(page: Page, targetPath = "/en/dashboard") {
  const isTargetUrl = (url: URL) => url.pathname === targetPath;

  await ensureBootstrapAdmin(page);

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

async function ensureBootstrapAdmin(page: Page) {
  const response = await page.request.post("/api/auth/bootstrap-admin", {
    data: {
      username,
      password,
      displayName: "E2E Admin",
    },
  });

  expect([201, 409]).toContain(response.status());
}
