import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

test.describe("Fleet Overview page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page, "/en/agents");
  });

  test("loads the fleet overview page", async ({ page }) => {
    await expect(page).toHaveURL(/\/en\/agents/);
    await expect(page.getByRole("heading", { name: "Agent Fleet" })).toBeVisible();
  });

  test("displays agent cards grouped by domain", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Product" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Requirement Manager/i })).toBeVisible();
  });

  test("filters agents by search query", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill("Requirement");
    await expect(searchInput).toHaveValue("Requirement");
    await expect(page.getByRole("button", { name: /Requirement Manager/i })).toBeVisible();
  });
});

test.describe("Agent Detail page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page, "/en/agents");
  });

  test("navigates to agent detail from fleet overview", async ({ page }) => {
    await page.getByRole("button", { name: /Requirement Manager/i }).click();
    await expect(page).toHaveURL(/\/en\/agents\/requirement-manager/);
  });

  test("displays agent detail with tabs", async ({ page }) => {
    await page.goto("/en/agents/requirement-manager");
    await expect(page.getByRole("heading", { name: "Requirement Manager" })).toBeVisible();
    await expect(page.getByRole("tab", { name: /overview/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /events/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /config/i })).toBeVisible();
  });

  test("navigates between agent detail tabs", async ({ page }) => {
    await page.goto("/en/agents/requirement-manager");
    await page.getByRole("tab", { name: /events/i }).click();
    await expect(page.getByRole("tabpanel")).toContainText("Extracted 3 new requirements");
    await page.getByRole("tab", { name: /config/i }).click();
    await expect(page.getByRole("tabpanel")).toContainText("Agent ID");
    await expect(page.getByRole("tabpanel")).toContainText("requirement-manager");
  });

  test("shows breadcrumb navigation on agent detail", async ({ page }) => {
    await page.goto("/en/agents/requirement-manager");
    const breadcrumb = page.getByRole("navigation", { name: /breadcrumb/i });
    await expect(breadcrumb.getByRole("link", { name: "Fleet" })).toBeVisible();
  });
});
