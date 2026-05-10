import { render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ControlPlaneAgentDefinition } from "@/entities/agent";
import type {
  ControlPlaneAgentRun,
  ControlPlaneApproval,
  ControlPlaneWorkItem,
} from "@/entities/control-plane";
import { GreetingBanner } from "./greeting-banner";

/**
 * DOM-level regression coverage for the home greeting banner.
 *
 * Pre-fix bug: `mapControlPlaneAgentStatus("active")` returned `"running"`,
 * which painted every catalog-enabled AgentRole as live. The "Running"
 * stat card on the home page would therefore mirror the count of seeded
 * agents (e.g. 5) instead of the actual in-flight run count (0).
 *
 * This spec stubs the control-plane API at the module boundary, renders
 * `<GreetingBanner />` with crafted fixtures matching production state
 * (catalog-active agents, no pending runs, no failed work, no pending
 * approvals), and asserts every stat card reads `0`.
 */

vi.mock("@/entities/agent/api/control-plane-agents", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/entities/agent/api/control-plane-agents")>();
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

function makeAgent(
  agentId: string,
  displayName: string,
  domain: string,
  status: string,
): ControlPlaneAgentDefinition {
  return {
    role_id: `role_${agentId}`,
    company_id: "cmp_projectcell",
    agent_id: agentId,
    display_name: displayName,
    agent_kind: "business_runtime_agent",
    interaction_mode: "internal",
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
    status,
    created_by: "test",
    metadata: {},
    created_at: NOW,
    updated_at: NOW,
  };
}

function makeSucceededRun(agentId: string): ControlPlaneAgentRun {
  return {
    run_id: `run_${agentId}`,
    company_id: "cmp_projectcell",
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
  };
}

function readStatValue(label: string): string | null {
  const labelEl = screen.getByText(label);
  const card = labelEl.closest("div.pt-6");
  return card?.querySelector("div.text-3xl")?.textContent ?? null;
}

describe("GreetingBanner", () => {
  beforeEach(() => {
    vi.mocked(listControlPlaneAgents).mockReset();
    vi.mocked(listControlPlaneApprovals).mockReset();
    vi.mocked(listControlPlaneRuns).mockReset();
    vi.mocked(listControlPlaneWorkItems).mockReset();
  });

  it("paints catalog-active agents with no live runs as Running=0", async () => {
    const agents = [
      makeAgent("requirement-manager", "Requirement Manager", "product", "active"),
      makeAgent("dev-agent", "Dev Agent", "engineering", "active"),
      makeAgent("qa-agent", "QA Agent", "quality", "active"),
      makeAgent("pjm-agent", "PJM Agent", "product", "active"),
      makeAgent("evolution-module", "Evolution Module", "data-ai", "active"),
    ];

    vi.mocked(listControlPlaneAgents).mockResolvedValue({
      agents,
      total: agents.length,
    });
    vi.mocked(listControlPlaneRuns).mockResolvedValue({
      runs: [makeSucceededRun("dev-agent")],
    });
    vi.mocked(listControlPlaneWorkItems).mockResolvedValue({
      work_items: [] as ControlPlaneWorkItem[],
      total: 0,
    });
    vi.mocked(listControlPlaneApprovals).mockResolvedValue({
      approvals: [] as ControlPlaneApproval[],
    });

    render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <GreetingBanner />
      </SWRConfig>,
    );

    await waitFor(() => {
      expect(readStatValue("stats.running")).toBe("0");
    });
    expect(readStatValue("stats.errors")).toBe("0");
    expect(readStatValue("stats.attention")).toBe("0");
    expect(readStatValue("stats.pendingApprovals")).toBe("0");
  });

  it("counts in-flight runs as Running > 0", async () => {
    const agents = [
      makeAgent("requirement-manager", "Requirement Manager", "product", "active"),
    ];
    const inflight: ControlPlaneAgentRun = {
      ...makeSucceededRun("requirement-manager"),
      status: "running",
      completed_at: null,
    };

    vi.mocked(listControlPlaneAgents).mockResolvedValue({
      agents,
      total: agents.length,
    });
    vi.mocked(listControlPlaneRuns).mockResolvedValue({
      runs: [inflight],
    });
    vi.mocked(listControlPlaneWorkItems).mockResolvedValue({
      work_items: [],
      total: 0,
    });
    vi.mocked(listControlPlaneApprovals).mockResolvedValue({
      approvals: [],
    });

    render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <GreetingBanner />
      </SWRConfig>,
    );

    await waitFor(() => {
      expect(readStatValue("stats.running")).toBe("1");
    });
  });
});
