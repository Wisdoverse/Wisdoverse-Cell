import { test, expect } from "@playwright/test";

/**
 * E2E test skeletons for the Agents pages (Fleet Overview + Agent Detail).
 *
 * These tests require a running dev server. They describe the intended
 * navigation flows and can be fully implemented once the backend is available.
 */

test.describe("Fleet Overview page", () => {
  test("loads the fleet overview page", async ({ page }) => {
    await page.goto("/en/agents");
    await expect(page).toHaveURL(/\/en\/agents/);
    // Should display the "Agent Fleet" heading
    const heading = page.getByText("Agent Fleet");
    await expect(heading).toBeVisible();
  });

  test("displays agent cards grouped by domain", async ({ page }) => {
    await page.goto("/en/agents");
    // Should show domain headers (e.g., "Product", "Engineering")
    const domainHeader = page.getByText("Product");
    await expect(domainHeader).toBeVisible();
  });

  test("filters agents by search query", async ({ page }) => {
    await page.goto("/en/agents");
    const searchInput = page.getByPlaceholder(/search/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill("Requirement");
      // Should filter to show only matching agents
    }
  });
});

test.describe("Agent Detail page", () => {
  test("navigates to agent detail from fleet overview", async ({ page }) => {
    await page.goto("/en/agents");
    // Click on the first agent card
    const firstCard = page.locator("button").first();
    if (await firstCard.isVisible()) {
      await firstCard.click();
      await expect(page).toHaveURL(/\/en\/agents\/.+/);
    }
  });

  test("displays agent detail with tabs", async ({ page }) => {
    await page.goto("/en/agents/requirement-manager");
    // Should show agent name and tabs
    const agentName = page.getByText("Requirement Manager");
    await expect(agentName).toBeVisible();
  });

  test("navigates between agent detail tabs", async ({ page }) => {
    await page.goto("/en/agents/requirement-manager");
    // Click on Events tab
    const eventsTab = page.getByRole("tab", { name: /events/i });
    if (await eventsTab.isVisible()) {
      await eventsTab.click();
    }
    // Click on Config tab
    const configTab = page.getByRole("tab", { name: /config/i });
    if (await configTab.isVisible()) {
      await configTab.click();
    }
  });

  test("shows breadcrumb navigation on agent detail", async ({ page }) => {
    await page.goto("/en/agents/requirement-manager");
    // Breadcrumb should show "Fleet > requirement-manager"
    const breadcrumb = page.getByText("Fleet");
    await expect(breadcrumb).toBeVisible();
  });
});
