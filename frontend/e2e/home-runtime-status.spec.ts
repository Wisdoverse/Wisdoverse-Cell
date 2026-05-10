import { test, expect, type Route } from "@playwright/test";
import { loginAsAdmin } from "./helpers/auth";

/**
 * Regression coverage for the home page runtime status pipeline.
 *
 * Pre-fix bug: `mapControlPlaneAgentStatus("active")` returned `"running"`,
 * which made every catalog-enabled AgentRole show as live on the home
 * dashboard with health=100, even when no AgentRun was in flight.
 *
 * This spec hermetically pins the upstream API responses to the exact
 * shape the production backend currently serves (5 active agents, 0 work
 * items, 0 pending approvals, 1 succeeded run) and asserts the home page
 * paints them as idle (Running=0, Errors=0). It will fail if the
 * lifecycle/runtime split regresses.
 */

const NOW = new Date().toISOString();

const seededAgent = (agentId: string, displayName: string, domain: string) => ({
  role_id: `role_${agentId}`,
  company_id: "cmp_e2e",
  agent_id: agentId,
  display_name: displayName,
  agent_kind: "business_runtime_agent" as const,
  interaction_mode: "direct" as const,
  role: agentId,
  title: displayName,
  domain,
  reports_to_agent_id: null,
  adapter_type: "builtin",
  adapter_config: {},
  context_sources: [],
  capabilities: [],
  responsibilities: [],
  subscribed_events: [],
  published_events: [],
  permissions: [],
  budget_policy_id: null,
  escalation_policy: {},
  status: "active",
  created_by: "e2e",
  metadata: {},
  created_at: NOW,
  updated_at: NOW,
});

const succeededRun = (agentId: string) => ({
  run_id: `run_${agentId}`,
  company_id: "cmp_e2e",
  agent_id: agentId,
  status: "succeeded",
  trace_id: null,
  goal_id: null,
  work_item_id: null,
  trigger_event_id: null,
  input_event: null,
  output_events: [],
  started_at: NOW,
  completed_at: NOW,
  error_category: null,
  error_message: null,
  last_successful_step: null,
  cost_usd: 0,
  input_tokens: 0,
  output_tokens: 0,
  metadata: {},
});

function fulfillJson(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

// Next.js dev server compiles routes on demand; the first hit on /en/login
// and /en/home can exceed the 30s default. Allow extra room for warmup.
test.describe.configure({ timeout: 180_000 });

test.describe("Home runtime status — catalog 'active' must not paint as 'running'", () => {
  test.beforeEach(async ({ page }) => {
    page.setDefaultNavigationTimeout(120_000);
    page.setDefaultTimeout(120_000);
    const agents = [
      seededAgent("requirement-manager", "Requirement Manager", "product"),
      seededAgent("dev-agent", "Dev Agent", "engineering"),
    ];
    const runs = [succeededRun("dev-agent")];

    await page.route("**/api/v1/control-plane/agents**", (route) =>
      fulfillJson(route, { agents, total: agents.length }),
    );
    await page.route("**/api/v1/control-plane/runs**", (route) =>
      fulfillJson(route, { runs, total: runs.length }),
    );
    await page.route("**/api/v1/control-plane/work-items**", (route) =>
      fulfillJson(route, { work_items: [], total: 0 }),
    );
    await page.route("**/api/v1/control-plane/approvals**", (route) =>
      fulfillJson(route, { approvals: [], total: 0 }),
    );

    await loginAsAdmin(page, "/en/home");
  });

  test("Running stat reads 0 when no run is in flight", async ({ page }) => {
    const runningValue = page
      .locator("p", { hasText: /^Running$/ })
      .locator("..")
      .locator("div.text-3xl")
      .first();
    await expect(runningValue).toHaveText("0");
  });

  test("Errors stat stays at 0 for a succeeded run", async ({ page }) => {
    const errorsValue = page
      .locator("p", { hasText: /^Errors$/ })
      .locator("..")
      .locator("div.text-3xl")
      .first();
    await expect(errorsValue).toHaveText("0");
  });

  test("Pending Approvals stat stays at 0 with no pending approvals", async ({ page }) => {
    const pendingValue = page
      .locator("p", { hasText: /^Pending Approvals$/ })
      .locator("..")
      .locator("div.text-3xl")
      .first();
    await expect(pendingValue).toHaveText("0");
  });
});
