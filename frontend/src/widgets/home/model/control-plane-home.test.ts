import { describe, expect, it } from "vitest";

import type {
  ControlPlaneAgentDefinition,
} from "@/entities/agent";
import type {
  ControlPlaneAgentRun,
  ControlPlaneWorkItem,
} from "@/entities/control-plane";
import { controlPlaneRuntimeForAgent } from "./control-plane-home";

const NOW = "2026-05-09T07:00:00.000Z";

function agent(status: string): ControlPlaneAgentDefinition {
  return {
    role_id: "role_test",
    company_id: "cmp_wisdoverse_cell",
    agent_id: "requirement-manager",
    display_name: "Requirement Manager",
    agent_kind: "business_runtime_agent",
    interaction_mode: "direct",
    role: "requirement-manager",
    title: "Requirement Manager",
    domain: "product",
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
    status,
    created_by: "test",
    metadata: {},
    created_at: NOW,
    updated_at: NOW,
  };
}

function run(status: ControlPlaneAgentRun["status"]): ControlPlaneAgentRun {
  return {
    run_id: "run_test",
    company_id: "cmp_wisdoverse_cell",
    agent_id: "requirement-manager",
    status,
    trace_id: null,
    goal_id: null,
    work_item_id: null,
    trigger_event_id: null,
    input_event: null,
    output_events: [],
    started_at: NOW,
    completed_at: status === "running" || status === "pending" ? null : NOW,
    error_category: null,
    error_message: null,
    last_successful_step: null,
    cost_usd: 0,
    input_tokens: 0,
    output_tokens: 0,
    metadata: {},
  };
}

function workItem(status: ControlPlaneWorkItem["status"]): ControlPlaneWorkItem {
  return {
    work_item_id: "work_test",
    company_id: "cmp_wisdoverse_cell",
    title: "Work",
    description: "",
    status,
    priority: "medium",
    goal_id: null,
    owner_agent_id: "requirement-manager",
    owner_user_id: null,
    source: "test",
    external_ref: null,
    dependencies: [],
    approval_required: false,
    metadata: {},
    created_at: NOW,
    updated_at: NOW,
  };
}

describe("controlPlaneRuntimeForAgent", () => {
  it("treats catalog-active agents with no runs as idle, not running", () => {
    // Regression guard: previously this returned `running` because the
    // catalog lifecycle flag `active` was conflated with runtime execution,
    // which painted every seeded agent as live on the home page.
    const runtime = controlPlaneRuntimeForAgent(agent("active"), [], []);

    expect(runtime.status).toBe("idle");
    expect(runtime.health).toBe(50);
    expect(runtime.task_count).toBe(0);
  });

  it("keeps paused lifecycle state visible instead of collapsing it to idle", () => {
    const runtime = controlPlaneRuntimeForAgent(agent("paused"), [], []);

    expect(runtime.status).toBe("paused");
    expect(runtime.health).toBe(0);
  });

  it("promotes to running when a run is in flight, regardless of lifecycle", () => {
    const runtime = controlPlaneRuntimeForAgent(agent("paused"), [run("running")], []);

    expect(runtime.status).toBe("running");
    expect(runtime.health).toBe(100);
  });

  it("surfaces runtime failures from runs and work items as error", () => {
    expect(controlPlaneRuntimeForAgent(agent("active"), [run("failed")], []).status).toBe(
      "error",
    );
    expect(controlPlaneRuntimeForAgent(agent("active"), [], [workItem("failed")]).status).toBe(
      "error",
    );
  });

  it("does not treat a succeeded run as ongoing execution", () => {
    const runtime = controlPlaneRuntimeForAgent(agent("active"), [run("succeeded")], []);

    expect(runtime.status).toBe("idle");
    expect(runtime.task_count).toBe(1);
  });
});
