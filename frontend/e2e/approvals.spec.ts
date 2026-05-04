import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

test.describe("Approvals page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page, "/en/approvals");
  });

  test("loads the approvals page", async ({ page }) => {
    await expect(page).toHaveURL(/\/en\/approvals/);
    await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
  });

  test("displays filter tabs", async ({ page }) => {
    await expect(page.getByRole("tab", { name: /all/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /finance/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /technical/i })).toBeVisible();
  });

  test("filters approvals by type tab", async ({ page }) => {
    await page.getByRole("tab", { name: /finance/i }).click();
    await expect(page.getByText("Q1 budget allocation review")).toBeVisible();
    await expect(page.getByText("Confirm requirement REQ-041")).toHaveCount(0);
  });

  test("shows approval cards with action buttons", async ({ page }) => {
    await expect(page.getByRole("button", { name: /approve/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /reject/i }).first()).toBeVisible();
  });

  test("navigates to approvals from home page", async ({ page }) => {
    await page.goto("/en/home");
    await page.getByRole("link", { name: /view all/i }).first().click();
    await expect(page).toHaveURL(/\/en\/approvals/);
  });
});
