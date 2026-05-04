import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

test.describe("Home page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page, "/en/home");
  });

  test("redirects root to /home", async ({ page }) => {
    await page.goto("/en");
    await expect(page).toHaveURL(/\/en\/home/);
  });

  test("displays greeting banner", async ({ page }) => {
    await expect(page.locator("h1")).toBeVisible();
  });

  test("displays agent fleet grid", async ({ page }) => {
    await expect(page.getByText("Agent Fleet")).toBeVisible();
  });

  test("navigates to fleet overview from home", async ({ page }) => {
    await page.getByRole("link", { name: "Fleet" }).click();
    await expect(page).toHaveURL(/\/en\/agents/);
  });

  test("displays pending approvals section", async ({ page }) => {
    await expect(page.getByText("Pending Approvals")).toBeVisible();
  });

  test("displays recent activity section", async ({ page }) => {
    await expect(page.getByText("Recent Activity")).toBeVisible();
  });
});
