import { render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ControlPlaneAgentDefinition } from "@/entities/agent";
import type {
  ControlPlaneAgentRun,
  ControlPlaneApproval,
  ControlPlaneWorkItem,
} from "@/entities/control-plane";
import { CommandCenter } from "./command-center";

vi.mock("@/entities/agent/api/control-plane-agents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/entities/agent/api/control-plane-agents")>();
  return {
    ...actual,
    listControlPlaneAgents: vi.fn(),
  };
});

vi.mock("@/entities/control-plane/api/control-plane", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/entities/control-plane/api/control-plane")>();
  return {
    ...actual,
    listControlPlaneApprovals: vi.fn(),
    listControlPlaneRuns: vi.fn(),
    listControlPlaneWorkItems: vi.fn(),
  };
});

import { listControlPlaneAgents } from "@/entities/agent/api/control-plane-agents";
import {
  listControlPlaneApprovals,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
} from "@/entities/control-plane/api/control-plane";

const NOW = "2026-05-09T07:00:00.000Z";

function makeAgent(): ControlPlaneAgentDefinition {
  return {
    role_id: "role_requirement-manager",
    company_id: "cmp_wisdoverse_cell",
    agent_id: "requirement-manager",
    display_name: "Requirement Manager",
    agent_kind: "business_runtime_agent",
    interaction_mode: "internal",
    role: "requirement-agent",
    title: "Requirement Manager Agent",
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
    status: "active",
    created_by: "test",
    metadata: {},
    created_at: NOW,
    updated_at: NOW,
  };
}

function makeRun(status: ControlPlaneAgentRun["status"]): ControlPlaneAgentRun {
  return {
    run_id: `run_${status}`,
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
    cost_usd: 1.5,
    input_tokens: 100,
    output_tokens: 50,
    metadata: {},
  };
}

function makeWorkItem(status: ControlPlaneWorkItem["status"]): ControlPlaneWorkItem {
  return {
    work_item_id: `work_${status}`,
    company_id: "cmp_wisdoverse_cell",
    title: "Review customer-risk deployment",
    description: "",
    status,
    priority: "high",
    goal_id: "goal_test",
    owner_agent_id: "requirement-manager",
    owner_user_id: null,
    source: "test",
    external_ref: null,
    dependencies: [],
    approval_required: status === "awaiting_approval",
    metadata: {},
    created_at: NOW,
    updated_at: NOW,
  };
}

function makeApproval(): ControlPlaneApproval {
  return {
    approval_id: "approval_test",
    company_id: "cmp_wisdoverse_cell",
    category: "technical",
    status: "pending",
    requested_by: "test",
    source_agent_id: "requirement-manager",
    proposed_action: "Approve deployment",
    reason: "Needs review",
    risk: "Low",
    rollback_note: "Rollback",
    affected_resources: [],
    artifact_links: [],
    run_id: null,
    work_item_id: null,
    goal_id: null,
    trace_id: null,
    resolved_by: null,
    resolved_at: null,
    expires_at: null,
    metadata: {},
    created_at: NOW,
    updated_at: NOW,
  };
}

function readMetric(label: string): string | null {
  const labelEl = screen.getByText(label);
  return labelEl.closest("div")?.querySelector(".text-3xl")?.textContent ?? null;
}

describe("CommandCenter", () => {
  beforeEach(() => {
    vi.mocked(listControlPlaneAgents).mockReset();
    vi.mocked(listControlPlaneApprovals).mockReset();
    vi.mocked(listControlPlaneRuns).mockReset();
    vi.mocked(listControlPlaneWorkItems).mockReset();
  });

  it("renders the operator command center with live queue and approval signals", async () => {
    vi.mocked(listControlPlaneAgents).mockResolvedValue({
      agents: [makeAgent()],
      total: 1,
    });
    vi.mocked(listControlPlaneRuns).mockResolvedValue({
      runs: [makeRun("running")],
    });
    vi.mocked(listControlPlaneWorkItems).mockResolvedValue({
      work_items: [makeWorkItem("blocked"), makeWorkItem("awaiting_approval")],
      total: 2,
    });
    vi.mocked(listControlPlaneApprovals).mockResolvedValue({
      approvals: [makeApproval()],
    });

    render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <CommandCenter />
      </SWRConfig>,
    );

    await waitFor(() => {
      expect(readMetric("stats.running")).toBe("1");
    });
    expect(readMetric("stats.attention")).toBe("3");
    expect(readMetric("stats.pendingApprovals")).toBe("1");
    expect(screen.getByText("focus.resolveBlockers.title")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /focus\.resolveBlockers\.cta/ })).toHaveAttribute(
      "href",
      "/en/workflows",
    );
    expect(screen.getByText("commandCenter.priorityTitle")).toBeInTheDocument();
    expect(screen.getByText("Review customer-risk deployment")).toBeInTheDocument();
  });
});
