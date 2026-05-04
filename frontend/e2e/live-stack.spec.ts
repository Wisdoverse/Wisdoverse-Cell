import { test, expect } from "@playwright/test";

test("backend health endpoint responds when a live stack URL is configured", async ({
  request,
}) => {
  const healthUrl = process.env.E2E_BACKEND_HEALTH_URL;
  test.skip(!healthUrl, "Set E2E_BACKEND_HEALTH_URL to include live backend health in E2E.");

  const response = await request.get(healthUrl!);
  expect(response.ok()).toBeTruthy();
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/json");
  expect(await response.json()).toMatchObject({ status: "alive" });
});
