import { test, expect } from "@playwright/test";

/**
 * E2E test skeletons for the requirements workflow.
 *
 * These tests are designed to run against a live dev server with a connected
 * backend.  Because we don't have a running backend in CI yet, the tests are
 * marked as TODO stubs – they describe the intended flow and can be fleshed
 * out once the full stack is available.
 */

test.describe("Requirements page", () => {
  test("navigates to the requirements list page", async ({ page }) => {
    // TODO: Replace with actual URL once auth flow is testable
    await page.goto("/en/requirements");

    // The page should contain a heading or breadcrumb for requirements.
    // Adjust the selector once the real page content is stable.
    await expect(page).toHaveURL(/requirements/);
  });

  test("requirement list loads and displays rows", async ({ page }) => {
    // TODO: Seed the database or mock the API before this test
    await page.goto("/en/requirements");

    // Wait for the table to appear (DataTable renders a <table> element)
    // const table = page.locator("table");
    // await expect(table).toBeVisible();

    // TODO: Verify that at least one row is rendered
    // const rows = table.locator("tbody tr");
    // await expect(rows.first()).toBeVisible();
  });

  test("confirm a requirement via row action", async () => {
    // TODO: Requires seeded data and authenticated session
    // await page.goto("/en/requirements");
    //
    // 1. Locate the confirm (check) button on the first row
    // const confirmBtn = page.locator("tbody tr").first().locator("button").first();
    // await confirmBtn.click();
    //
    // 2. Confirm dialog should appear
    // await expect(page.getByRole("dialog")).toBeVisible();
    //
    // 3. Click the confirm button in the dialog
    // await page.getByRole("button", { name: /confirm/i }).click();
    //
    // 4. The row status badge should update to "confirmed"
    // await expect(page.locator("tbody tr").first()).toContainText("confirmed");
  });

  test("reject a requirement via row action", async () => {
    // TODO: Requires seeded data and authenticated session
    // await page.goto("/en/requirements");
    //
    // 1. Locate the reject (X) button on the first row
    // const rejectBtn = page.locator("tbody tr").first().locator("button").nth(1);
    // await rejectBtn.click();
    //
    // 2. Reject sheet should open
    // await expect(page.getByRole("dialog")).toBeVisible();
    //
    // 3. Fill in a rejection reason
    // await page.getByRole("textbox").fill("Not in scope for MVP");
    //
    // 4. Submit
    // await page.getByRole("button", { name: /reject/i }).click();
    //
    // 5. Row should update
    // await expect(page.locator("tbody tr").first()).toContainText("rejected");
  });

  test("bulk select and confirm multiple requirements", async () => {
    // TODO: Requires seeded data and authenticated session
    // await page.goto("/en/requirements");
    //
    // 1. Click the header checkbox to select all
    // const headerCheckbox = page.locator("thead input[type='checkbox']");
    // await headerCheckbox.check();
    //
    // 2. Click the batch confirm action
    // await page.getByRole("button", { name: /confirm selected/i }).click();
    //
    // 3. Verify all rows are updated
  });
});
