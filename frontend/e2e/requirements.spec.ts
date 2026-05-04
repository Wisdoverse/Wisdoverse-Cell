import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

test.describe("Requirements page", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page, "/en/requirements");
  });

  test("loads the requirements list page", async ({ page }) => {
    await expect(page).toHaveURL(/\/en\/requirements/);
    await expect(page.getByRole("heading", { name: "Requirements" })).toBeVisible();
  });

  test("displays list filters and table shell", async ({ page }) => {
    await expect(page.getByText("All Status")).toBeVisible();
    await expect(page.getByText("All Priority")).toBeVisible();
    await expect(page.getByText("All Category")).toBeVisible();
    await expect(page.getByPlaceholder("Semantic search...")).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
  });

  test("keeps the operator on the list when changing a filter", async ({ page }) => {
    await page.getByText("All Status").click();
    await page.getByRole("option", { name: "Pending" }).click();

    await expect(page).toHaveURL(/\/en\/requirements/);
    await expect(page.getByText("Pending")).toBeVisible();
  });
});
