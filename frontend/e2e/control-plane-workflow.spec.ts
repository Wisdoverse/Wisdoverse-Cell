import { expect, test, type Page } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

const goal = {
  goal_id: "goal_e2e", company_id: "company_e2e", title: "E2E goal", description: "",
  status: "active", parent_goal_id: null, owner_agent_id: "pjm-agent", owner_user_id: null,
  success_metric: "accepted output", target_value: 1, current_value: 0, due_at: null,
  tags: [], metadata: {}, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

function workItem(status: string, metadata: Record<string, unknown> = {}, title = "E2E work", ownerAgentId = "dev-agent", approvalRequired = false) {
  return {
    work_item_id: "work_e2e", company_id: "company_e2e", title, description: "",
    status, priority: "medium", goal_id: goal.goal_id, owner_agent_id: ownerAgentId, owner_user_id: null,
    source: "manual", external_ref: null, dependencies: [], approval_required: approvalRequired, metadata,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

async function mockControlPlane(page: Page, options: { denial?: boolean; initialStatus?: string; approval?: boolean; failFirstRun?: boolean } = {}) {
  let status = options.initialStatus ?? "ready";
  let accepted = false;
  let hasRun = false;
  let title = "E2E work";
  let ownerAgentId = "dev-agent";
  let approvalStatus = options.approval ? "pending" : "none";
  const executionKey = "execution-key-e2e";
  let runAttempts = 0;
  const requests: Array<{ path: string; body: Record<string, unknown> }> = [];
  const currentWorkItem = (metadata: Record<string, unknown> = {}) => workItem(status, metadata, title, ownerAgentId, Boolean(options.approval));
  await page.route("**/api/operator/control-plane/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/operator", "");
    if (request.method() === "GET" && path === "/control-plane/operating-metrics") {
      return route.fulfill({ json: {
        company_id: "company_e2e", as_of_utc: "2026-10-01T00:00:00Z",
        export_policy: { retention_days: 90, applies_to: "exported snapshots" },
        runs: { total: 0, by_status: {}, success_rate: null, adapter_errors: 0 },
        queue_delay: { p95_seconds: null, sample_size: 0, sample_limit: 1000, sampled_work_items: 0, excluded_without_run: 0, source: "work item create to first associated run" },
        approvals: { pending: 0, oldest_pending_age_seconds: null },
        costs: { accepted_outcome_count: 0, full_cost_usd_total: 0, full_cost_usd_per_accepted_outcome: null, full_cost_basis: "max of run and budget usage totals", run_reported_cost_usd_total: 0, deduplicated_budget_usage_usd_total: 0, failed_run_reported_cost_usd: 0, failed_run_budget_charges_usd: 0, estimated_ceiling_usd_total: 0, estimated_ceiling_usd_per_accepted_outcome: null, estimated_execution_count: 0, unestimated_execution_count: 0, budget_usage_run_coverage: 0, run_cost_coverage: 0, unmetered_run_count: 0 },
        unresolved_execution_leases: { count: 0, oldest_age_seconds: null },
        pending_outbox: { count: 0, oldest_age_seconds: null },
      } });
    }
    if (request.method() === "GET" && path === "/control-plane/goals") {
      return route.fulfill({ json: { goals: [goal], total: 1 } });
    }
    if (request.method() === "GET" && path === "/control-plane/work-items") {
      return route.fulfill({ json: { work_items: [currentWorkItem(accepted ? { accepted_artifact_id: "artifact_e2e" } : {})], total: 1 } });
    }
    if (request.method() === "GET" && path === "/control-plane/runs") {
      return route.fulfill({ json: { runs: hasRun ? [{ run_id: "run_e2e", company_id: "company_e2e", agent_id: "dev-agent", status: "succeeded", trace_id: "trace_e2e", goal_id: goal.goal_id, work_item_id: "work_e2e", trigger_event_id: null, input_event: null, output_events: [], started_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:01:00Z", error_category: null, error_message: null, last_successful_step: null, cost_usd: 0.1, input_tokens: 1, output_tokens: 1, metadata: { adapter_type: "http" } }] : [] } });
    }
    if (request.method() === "GET" && path === "/control-plane/artifacts") {
      return route.fulfill({ json: { artifacts: hasRun ? [{ artifact_id: "artifact_e2e", company_id: "company_e2e", artifact_type: "report", title: "E2E artifact", uri: "/artifact-e2e", content_hash: null, run_id: "run_e2e", work_item_id: "work_e2e", goal_id: goal.goal_id, created_by_agent_id: "dev-agent", metadata: {}, created_at: "2026-01-01T00:01:00Z" }] : [], total: hasRun ? 1 : 0 } });
    }
    if (request.method() === "GET" && path === "/control-plane/decisions") return route.fulfill({ json: { decisions: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/approvals") return route.fulfill({ json: { approvals: approvalStatus === "none" ? [] : [{ approval_id: "approval_e2e", company_id: "company_e2e", work_item_id: "work_e2e", source_agent_id: ownerAgentId, proposed_action: "Run E2E work", reason: "Required operator review", status: approvalStatus, metadata: approvalStatus === "approved" ? { execution_key: executionKey } : {}, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" }], total: approvalStatus === "none" ? 0 : 1 } });
    if (request.method() === "GET" && path === "/control-plane/budgets/usage") return route.fulfill({ json: { usage: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/timeline") return route.fulfill({ json: { timeline: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/evolution-proposals") return route.fulfill({ json: { evolution_proposals: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/budgets/policies") return route.fulfill({ json: { budget_policies: [], total: 0 } });
    if (request.method() === "POST" && path === "/control-plane/work-items") {
      const body = request.postDataJSON();
      requests.push({ path, body });
      title = body.title;
      ownerAgentId = body.owner_agent_id;
      status = body.status;
      return route.fulfill({ json: currentWorkItem() });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/reassign") {
      const body = request.postDataJSON();
      requests.push({ path, body });
      ownerAgentId = body.owner_agent_id;
      return route.fulfill({ json: currentWorkItem() });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/run") {
      const body = request.postDataJSON();
      requests.push({ path, body });
      if (options.denial || (options.approval && approvalStatus !== "approved")) return route.fulfill({ status: 403, json: { detail: "execution_permission_denied" } });
      if (body.company_id !== "company_e2e") {
        return route.fulfill({ status: 403, json: { detail: "operator_scope_denied" } });
      }
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(body.idempotency_key)) {
        return route.fulfill({ status: 422, json: { detail: "idempotency_key_required" } });
      }
      runAttempts += 1;
      if (options.failFirstRun && runAttempts === 1) {
        hasRun = true;
        status = "failed";
        return route.fulfill({ json: { work_item: currentWorkItem(), run: { run_id: "run_e2e" }, output: "attempt failed" } });
      }
      hasRun = true;
      status = "awaiting_approval";
      return route.fulfill({ json: { work_item: currentWorkItem(), run: { run_id: "run_e2e" }, output: "ready for review", evidence_artifact_id: "artifact_e2e" } });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/retry") {
      const body = request.postDataJSON();
      requests.push({ path, body });
      runAttempts += 1;
      hasRun = true;
      status = "awaiting_approval";
      return route.fulfill({ json: { work_item: currentWorkItem(), run: { run_id: "run_e2e" }, output: "retry ready for review", evidence_artifact_id: "artifact_e2e" } });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/accept") {
      const body = request.postDataJSON();
      requests.push({ path, body });
      if (body.company_id !== "company_e2e") return route.fulfill({ status: 403, json: { detail: "operator_scope_denied" } });
      if (body.verdict !== "accepted" || !body.reason?.trim()) return route.fulfill({ status: 422, json: { detail: "review_reason_required" } });
      accepted = true;
      return route.fulfill({ json: { work_item: currentWorkItem({ accepted_artifact_id: body.verdict === "accepted" ? "artifact_e2e" : undefined }), acceptance: { verdict: body.verdict } } });
    }
    if (request.method() === "POST" && path.startsWith("/control-plane/approvals/")) {
      const body = request.postDataJSON();
      requests.push({ path, body });
      approvalStatus = path.endsWith("/approve") ? "approved" : "rejected";
      return route.fulfill({ json: {} });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/close") {
      if (!accepted) return route.fulfill({ status: 409, json: { detail: "accepted_artifact_required" } });
      status = "completed";
      return route.fulfill({ json: currentWorkItem({ accepted_artifact_id: "artifact_e2e" }) });
    }
    return route.fulfill({ json: {} });
  });
  return { requests };
}

test.describe("Control-plane work lifecycle", () => {
  test("runs work, accepts its artifact with a reason, then closes it", async ({ page }) => {
    await mockControlPlane(page);
    await loginAsAdmin(page, "/en/workflows");
    await expect(page.getByRole("button", { name: "Run work" })).toBeVisible();
    await page.getByRole("button", { name: "Run work" }).click();
    await page.getByRole("tab", { name: "Artifacts" }).click();
    await expect(page.getByText("E2E artifact")).toBeVisible();
    await page.getByLabel("Reviewer reason").fill("QA evidence reviewed and accepted");
    await page.getByRole("button", { name: "Accept artifact" }).click();
    await expect(page.getByRole("button", { name: "Close accepted work" })).toBeVisible();
    await page.getByRole("button", { name: "Close accepted work" }).click();
    await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  });

  test("shows a denied execution permission error", async ({ page }) => {
    await mockControlPlane(page, { denial: true });
    await loginAsAdmin(page, "/en/workflows");
    await page.getByRole("button", { name: "Run work" }).click();
    await expect(page.getByText("execution_permission_denied", { exact: true })).toBeVisible();
  });

  test("creates work under the selected goal and reassigns it from the visible edit form", async ({ page }) => {
    const mock = await mockControlPlane(page);
    await loginAsAdmin(page, "/en/workflows");
    await page.getByRole("button", { name: "New Work" }).click();
    await page.getByLabel("Work item title").fill("Prepare weekly operating report");
    await page.getByLabel("Owner agent").fill("dev-agent");
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.getByText("Prepare weekly operating report", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Edit Work" }).click();
    await page.getByLabel("Owner agent").fill("qa-agent");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("qa-agent", { exact: true })).toBeVisible();

    const created = mock.requests.find((request) => request.path === "/control-plane/work-items");
    expect(created?.body).toMatchObject({
      title: "Prepare weekly operating report",
      goal_id: goal.goal_id,
      owner_agent_id: "dev-agent",
      status: "ready",
    });
    expect(mock.requests.find((request) => request.path.endsWith("/reassign"))?.body).toMatchObject({
      company_id: "company_e2e",
      owner_agent_id: "qa-agent",
      actor_id: "human:operator",
    });
  });

  test("offers retry after a failed run and submits the retry through the work-item route", async ({ page }) => {
    const mock = await mockControlPlane(page, { failFirstRun: true });
    await loginAsAdmin(page, "/en/workflows");
    await page.getByRole("button", { name: "Run work" }).click();
    await expect(page.getByText("Failed", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Retry failed run" }).click();
    await expect(page.getByText("Needs approval", { exact: true })).toBeVisible();

    expect(mock.requests.filter((request) => request.path.endsWith("/run"))).toHaveLength(1);
    expect(mock.requests.find((request) => request.path.endsWith("/retry"))?.body).toMatchObject({
      company_id: "company_e2e",
      actor_id: "human:operator",
    });
  });

  test("keeps approval-required work blocked after an operator rejects approval", async ({ page }) => {
    const mock = await mockControlPlane(page, { initialStatus: "awaiting_approval", approval: true });
    await loginAsAdmin(page, "/en/workflows");
    await expect(page.getByText("This work item is waiting for required human approval.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Run work" })).toHaveCount(0);

    await page.getByRole("tab", { name: "Approvals" }).click();
    await page.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(page.getByText("Rejected", { exact: true })).toBeVisible();
    expect(mock.requests.find((request) => request.path.endsWith("/reject"))?.body).toMatchObject({ resolved_by: "human:operator" });
    await expect(page.getByRole("button", { name: "Run work" })).toHaveCount(0);
    expect(mock.requests.filter((request) => request.path.endsWith("/run"))).toHaveLength(0);
  });

  test("reuses the approved execution key when running approval-required work", async ({ page }) => {
    const mock = await mockControlPlane(page, { initialStatus: "awaiting_approval", approval: true });
    await loginAsAdmin(page, "/en/workflows");
    await expect(page.getByText("This work item is waiting for required human approval.")).toBeVisible();
    await page.getByRole("tab", { name: "Approvals" }).click();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("Approval is bound to this execution intent. Resubmission will reuse its execution key.")).toBeVisible();
    await page.getByRole("button", { name: "Run work" }).click();

    expect(mock.requests.find((request) => request.path.endsWith("/approve"))?.body).toMatchObject({ resolved_by: "human:operator" });
    expect(mock.requests.find((request) => request.path.endsWith("/run"))?.body).toMatchObject({ idempotency_key: "execution-key-e2e" });
  });

  test("submits artifact rejection with the reviewer reason", async ({ page }) => {
    const mock = await mockControlPlane(page);
    await loginAsAdmin(page, "/en/workflows");
    await page.getByRole("button", { name: "Run work" }).click();
    await page.getByRole("tab", { name: "Artifacts" }).click();
    await page.getByLabel("Reviewer reason").fill("Evidence does not meet the acceptance criteria");
    await page.getByRole("button", { name: "Reject artifact" }).click();
    expect(mock.requests.find((request) => request.path.endsWith("/accept"))?.body).toMatchObject({
      verdict: "rejected",
      reason: "Evidence does not meet the acceptance criteria",
      artifact_id: "artifact_e2e",
    });
  });
});
