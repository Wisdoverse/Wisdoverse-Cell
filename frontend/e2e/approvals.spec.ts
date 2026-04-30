import { test, expect } from "@playwright/test";

/**
 * E2E test skeletons for the Approvals page (Unified Approval Center).
 *
 * These tests require a running dev server with backend.
 */

test.describe("Approvals page", () => {
  test("loads the approvals page", async ({ page }) => {
    await page.goto("/en/approvals");
    await expect(page).toHaveURL(/\/en\/approvals/);
    // Should display the "Approval Center" heading
    const heading = page.getByText("Approval Center");
    await expect(heading).toBeVisible();
  });

  test("displays filter tabs", async ({ page }) => {
    await page.goto("/en/approvals");
    // Should show filter tabs: All, Finance, Legal, Technical, Customer
    const allTab = page.getByRole("tab", { name: /all/i });
    await expect(allTab).toBeVisible();
  });

  test("filters approvals by type tab", async ({ page }) => {
    await page.goto("/en/approvals");
    // Click on Finance tab
    const financeTab = page.getByRole("tab", { name: /finance/i });
    if (await financeTab.isVisible()) {
      await financeTab.click();
      // Should filter to show only finance approvals
    }
  });

  test("shows approval cards with action buttons", async ({ page }) => {
    await page.goto("/en/approvals");
    // Should display approval cards with Approve/Reject buttons
    const approveButton = page.getByRole("button", { name: /approve/i }).first();
    await expect(approveButton).toBeVisible();
  });

  test("navigates to approvals from home page", async ({ page }) => {
    await page.goto("/en/home");
    // Click "View All" link in pending approvals section
    const viewAllLink = page.getByRole("link", { name: /view all/i }).first();
    if (await viewAllLink.isVisible()) {
      await viewAllLink.click();
      await expect(page).toHaveURL(/\/en\/approvals/);
    }
  });
});
