import { test, expect } from "@playwright/test";

/**
 * E2E test skeletons for the Home page (Command Center).
 *
 * These tests require a running dev server. They describe the intended
 * flows and can be fully implemented once the backend is available.
 */

test.describe("Home page", () => {
  test("redirects root to /home", async ({ page }) => {
    await page.goto("/en");
    await expect(page).toHaveURL(/\/en\/home/);
  });

  test("displays greeting banner", async ({ page }) => {
    await page.goto("/en/home");
    // The greeting banner should show a time-based greeting
    const greeting = page.locator("h1");
    await expect(greeting).toBeVisible();
  });

  test("displays agent fleet grid", async ({ page }) => {
    await page.goto("/en/home");
    // The fleet grid should show agent cards grouped by domain
    const fleetSection = page.getByText("Agent Fleet");
    await expect(fleetSection).toBeVisible();
  });

  test("navigates to fleet overview from home", async ({ page }) => {
    await page.goto("/en/home");
    // Click "View All" link in fleet section
    const viewAllLink = page.getByRole("link", { name: /view all/i });
    if (await viewAllLink.isVisible()) {
      await viewAllLink.click();
      await expect(page).toHaveURL(/\/en\/agents/);
    }
  });

  test("displays pending approvals section", async ({ page }) => {
    await page.goto("/en/home");
    const approvalsSection = page.getByText("Pending Approvals");
    await expect(approvalsSection).toBeVisible();
  });

  test("displays recent activity section", async ({ page }) => {
    await page.goto("/en/home");
    const activitySection = page.getByText("Recent Activity");
    await expect(activitySection).toBeVisible();
  });
});
