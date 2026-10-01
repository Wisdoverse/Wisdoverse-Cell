import { expect, test } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

/**
 * Opt-in full-stack acceptance for an isolated PostgreSQL-backed Control Plane.
 * Unlike control-plane-workflow.spec.ts, this spec never intercepts API calls:
 * the browser uses the authenticated Next.js operator proxy and asserts the
 * durable objects returned by the real backend.
 */
const enabled = process.env.REAL_CONTROL_PLANE_E2E === "1";
const goalId = process.env.REAL_CONTROL_PLANE_GOAL_ID ?? "g_browser";
const companyId = process.env.REAL_CONTROL_PLANE_COMPANY_ID ?? "cmp_roadmap_browser";
const ownerAgentId = process.env.REAL_CONTROL_PLANE_AGENT_ID ?? "dev-browser";

test.describe.configure({ timeout: 180_000 });
test.skip(!enabled, "Set REAL_CONTROL_PLANE_E2E=1 against the isolated real Control Plane fixture.");

test("creates, assigns, executes, reviews, and closes work with persisted backend evidence", async ({ page }) => {
  // The proxy requires an Origin check on writes. Keep it explicit in this
  // isolated browser fixture so the request carries the same origin as the
  // page even when the installed headless Chromium omits it on same-origin
  // fetches.
  const browserOrigin = new URL(
    process.env.PLAYWRIGHT_BASE_URL ??
      `http://127.0.0.1:${process.env.PLAYWRIGHT_PORT ?? "3100"}`,
  ).origin;
  await page.setExtraHTTPHeaders({ origin: browserOrigin });
  const title = `Browser acceptance ${new Date().toISOString()}`;
  const reviewerReason = "Inspected the real run output and accepted the evidence.";

  await loginAsAdmin(page, "/en/workflows");

  const goalsResponse = await page.request.get("/api/operator/control-plane/goals?limit=100");
  expect(goalsResponse.status()).toBe(200);
  const goals = await goalsResponse.json();
  expect(goals.goals.some((item: { goal_id: string }) => item.goal_id === goalId)).toBeTruthy();

  // Create from the visible operator flow. The fixture supplies the goal and a
  // local-process agent; assignment is then changed through the edit dialog.
  await expect(page.getByRole("button", { name: "New Work" })).toBeEnabled();
  await page.getByRole("button", { name: "New Work" }).click();
  await page.getByLabel("Work item title").fill(title);
  await page.getByLabel("Description").fill("Produce and review a real backend acceptance artifact.");
  await page.getByRole("button", { name: "Create", exact: true }).click();

  await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Edit Work" }).click();
  await page.getByLabel("Owner agent").fill(ownerAgentId);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(ownerAgentId, { exact: true })).toBeVisible();

  const workItemsBeforeRunResponse = await page.request.get(
    `/api/operator/control-plane/work-items?goal_id=${encodeURIComponent(goalId)}&limit=100`,
  );
  expect(workItemsBeforeRunResponse.status()).toBe(200);
  const workItemsBeforeRun = await workItemsBeforeRunResponse.json();
  const createdWorkItem = workItemsBeforeRun.work_items.find((item: { title: string }) => item.title === title);
  expect(createdWorkItem).toMatchObject({
    company_id: companyId,
    goal_id: goalId,
    owner_agent_id: ownerAgentId,
    status: "ready",
  });
  const workItemId = createdWorkItem.work_item_id as string;

  // Run through the visible action; wait for the actual backend run and inspect
  // the linked run, generated artifact, charged usage, and timeline records.
  await page.getByRole("button", { name: "Run work" }).click();
  await page.getByRole("tab", { name: "Artifacts" }).click();
  await expect(page.getByText("Run walkthrough", { exact: true })).toBeVisible({ timeout: 60_000 });

  const runsResponse = await page.request.get(
    `/api/operator/control-plane/runs?work_item_id=${encodeURIComponent(workItemId)}&limit=20`,
  );
  expect(runsResponse.status()).toBe(200);
  const runs = await runsResponse.json();
  const run = runs.runs.find((item: { work_item_id: string }) => item.work_item_id === workItemId);
  expect(run).toMatchObject({
    company_id: companyId,
    goal_id: goalId,
    work_item_id: workItemId,
    agent_id: ownerAgentId,
    status: "succeeded",
  });
  expect(run.cost_usd).toBeGreaterThan(0);
  const runId = run.run_id as string;

  const artifactsResponse = await page.request.get(
    `/api/operator/control-plane/artifacts?work_item_id=${encodeURIComponent(workItemId)}&run_id=${encodeURIComponent(runId)}&limit=20`,
  );
  expect(artifactsResponse.status()).toBe(200);
  const artifacts = await artifactsResponse.json();
  const artifact = artifacts.artifacts.find((item: { run_id: string }) => item.run_id === runId);
  expect(artifact).toMatchObject({
    company_id: companyId,
    goal_id: goalId,
    work_item_id: workItemId,
    run_id: runId,
    artifact_type: "run_walkthrough",
  });
  expect(artifact.content_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(artifact.uri).toContain(runId);

  const usageResponse = await page.request.get(
    `/api/operator/control-plane/budgets/usage?run_id=${encodeURIComponent(runId)}&limit=100`,
  );
  expect(usageResponse.status()).toBe(200);
  const usage = await usageResponse.json();
  expect(usage.usage.length).toBeGreaterThan(0);
  expect(usage.usage.some((item: { run_id: string; cost_usd: number }) => item.run_id === runId && item.cost_usd > 0)).toBeTruthy();

  const timelineResponse = await page.request.get(
    `/api/operator/control-plane/timeline?run_id=${encodeURIComponent(runId)}&limit=100`,
  );
  expect(timelineResponse.status()).toBe(200);
  const timeline = await timelineResponse.json();
  expect(timeline.timeline.some((item: { type: string; data?: Record<string, unknown> }) => item.type === "agent_run" && item.data?.run_id === runId)).toBeTruthy();
  expect(timeline.timeline.some((item: { type: string; data?: Record<string, unknown> }) => item.type === "artifact" && item.data?.artifact_id === artifact.artifact_id)).toBeTruthy();

  // Review the actual artifact in the UI and close only after acceptance.
  await page.getByLabel("Reviewer reason").fill(reviewerReason);
  await page.getByRole("button", { name: "Accept artifact" }).click();
  await expect(page.getByRole("button", { name: "Close accepted work" })).toBeVisible();
  await page.getByRole("button", { name: "Close accepted work" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();

  const finalWorkItemsResponse = await page.request.get(
    `/api/operator/control-plane/work-items?goal_id=${encodeURIComponent(goalId)}&limit=100`,
  );
  expect(finalWorkItemsResponse.status()).toBe(200);
  const finalWorkItems = await finalWorkItemsResponse.json();
  const completedWorkItem = finalWorkItems.work_items.find((item: { work_item_id: string }) => item.work_item_id === workItemId);
  expect(completedWorkItem).toMatchObject({
    company_id: companyId,
    goal_id: goalId,
    owner_agent_id: ownerAgentId,
    status: "completed",
  });
  expect(completedWorkItem.metadata.accepted_artifact_id).toBe(artifact.artifact_id);

  const activityResponse = await page.request.get(
    `/api/operator/control-plane/work-items/${encodeURIComponent(workItemId)}/activity?limit=100`,
  );
  expect(activityResponse.status()).toBe(200);
  const activity = await activityResponse.json();
  expect(activity.activity.some((item: { type: string; data?: { action?: string; detail?: Record<string, unknown>; run_id?: string } }) =>
    item.type === "audit_event" && item.data?.action === "outcome.accepted" &&
    item.data.run_id === runId && item.data.detail?.reason === reviewerReason,
  )).toBeTruthy();
});
