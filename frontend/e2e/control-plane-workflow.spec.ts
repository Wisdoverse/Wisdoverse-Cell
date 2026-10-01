import { expect, test, type Page } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

const goal = {
  goal_id: "goal_e2e", company_id: "company_e2e", title: "E2E goal", description: "",
  status: "active", parent_goal_id: null, owner_agent_id: "pjm-agent", owner_user_id: null,
  success_metric: "accepted output", target_value: 1, current_value: 0, due_at: null,
  tags: [], metadata: {}, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

function workItem(status: string, metadata: Record<string, unknown> = {}) {
  return {
    work_item_id: "work_e2e", company_id: "company_e2e", title: "E2E work", description: "",
    status, priority: "medium", goal_id: goal.goal_id, owner_agent_id: "dev-agent", owner_user_id: null,
    source: "manual", external_ref: null, dependencies: [], approval_required: false, metadata,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

async function mockControlPlane(page: Page, denial = false) {
  let status = "ready";
  let accepted = false;
  let hasRun = false;
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
      return route.fulfill({ json: { work_items: [workItem(status, accepted ? { accepted_artifact_id: "artifact_e2e" } : {})], total: 1 } });
    }
    if (request.method() === "GET" && path === "/control-plane/runs") {
      return route.fulfill({ json: { runs: hasRun ? [{ run_id: "run_e2e", company_id: "company_e2e", agent_id: "dev-agent", status: "succeeded", trace_id: "trace_e2e", goal_id: goal.goal_id, work_item_id: "work_e2e", trigger_event_id: null, input_event: null, output_events: [], started_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:01:00Z", error_category: null, error_message: null, last_successful_step: null, cost_usd: 0.1, input_tokens: 1, output_tokens: 1, metadata: { adapter_type: "http" } }] : [] } });
    }
    if (request.method() === "GET" && path === "/control-plane/artifacts") {
      return route.fulfill({ json: { artifacts: hasRun ? [{ artifact_id: "artifact_e2e", company_id: "company_e2e", artifact_type: "report", title: "E2E artifact", uri: "/artifact-e2e", content_hash: null, run_id: "run_e2e", work_item_id: "work_e2e", goal_id: goal.goal_id, created_by_agent_id: "dev-agent", metadata: {}, created_at: "2026-01-01T00:01:00Z" }] : [], total: hasRun ? 1 : 0 } });
    }
    if (request.method() === "GET" && path === "/control-plane/decisions") return route.fulfill({ json: { decisions: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/approvals") return route.fulfill({ json: { approvals: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/budgets/usage") return route.fulfill({ json: { usage: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/timeline") return route.fulfill({ json: { timeline: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/evolution-proposals") return route.fulfill({ json: { evolution_proposals: [], total: 0 } });
    if (request.method() === "GET" && path === "/control-plane/budgets/policies") return route.fulfill({ json: { budget_policies: [], total: 0 } });
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/run") {
      if (denial) return route.fulfill({ status: 403, json: { detail: "execution_permission_denied" } });
      const body = request.postDataJSON();
      if (body.company_id !== "company_e2e") {
        return route.fulfill({ status: 403, json: { detail: "operator_scope_denied" } });
      }
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(body.idempotency_key)) {
        return route.fulfill({ status: 422, json: { detail: "idempotency_key_required" } });
      }
      hasRun = true;
      status = "awaiting_approval";
      return route.fulfill({ json: { work_item: workItem(status), run: { run_id: "run_e2e" }, output: "ready for review", evidence_artifact_id: "artifact_e2e" } });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/accept") {
      const body = request.postDataJSON();
      if (body.company_id !== "company_e2e") return route.fulfill({ status: 403, json: { detail: "operator_scope_denied" } });
      if (body.verdict !== "accepted" || !body.reason?.trim()) return route.fulfill({ status: 422, json: { detail: "review_reason_required" } });
      accepted = true;
      return route.fulfill({ json: { work_item: workItem(status, { accepted_artifact_id: "artifact_e2e" }), acceptance: { verdict: "accepted" } } });
    }
    if (request.method() === "POST" && path === "/control-plane/work-items/work_e2e/close") {
      if (!accepted) return route.fulfill({ status: 409, json: { detail: "accepted_artifact_required" } });
      status = "completed";
      return route.fulfill({ json: workItem(status, { accepted_artifact_id: "artifact_e2e" }) });
    }
    if (request.method() === "POST" && path.startsWith("/control-plane/approvals/")) return route.fulfill({ json: {} });
    return route.fulfill({ json: {} });
  });
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
    await mockControlPlane(page, true);
    await loginAsAdmin(page, "/en/workflows");
    await page.getByRole("button", { name: "Run work" }).click();
    await expect(page.getByText("execution_permission_denied", { exact: true })).toBeVisible();
  });
});
