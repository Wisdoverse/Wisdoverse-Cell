import { render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getAgentPromptConfig,
  getControlPlaneAgent,
  listControlPlaneAgents,
} from "@/entities/agent/api/control-plane-agents";
import type { ControlPlaneAgentDefinition } from "@/entities/agent";
import { AgentDetailPage } from "./agent-detail-page";

vi.mock("@/entities/agent/api/control-plane-agents", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/entities/agent/api/control-plane-agents")>();
  return {
    ...actual,
    getAgentPromptConfig: vi.fn(),
    getControlPlaneAgent: vi.fn(),
    listControlPlaneAgents: vi.fn(),
  };
});

const requirementManager: ControlPlaneAgentDefinition = {
  role_id: "role_requirement_manager",
  company_id: "cmp_projectcell",
  agent_id: "requirement-manager",
  display_name: "Requirement Manager",
  agent_kind: "business_runtime_agent",
  interaction_mode: "internal",
  role: "requirement-agent",
  title: "Requirement Manager Agent",
  domain: "product",
  reports_to_agent_id: "cpo",
  adapter_type: "builtin",
  adapter_config: {
    execution_mode: "runtime_module",
    package_path: "agents.requirement_manager",
  },
  context_sources: ["feishu", "manual_upload", "control_plane"],
  capabilities: ["Requirement extraction"],
  responsibilities: ["Manage requirement confirmation workflows."],
  subscribed_events: ["coordinator.dispatch"],
  published_events: ["requirement.confirmed"],
  permissions: [],
  budget_policy_id: null,
  escalation_policy: {},
  status: "active",
  created_by: "bootstrap",
  metadata: {},
  created_at: "2026-05-08T00:00:00Z",
  updated_at: "2026-05-08T00:00:00Z",
};

function renderDetail(agentId: string) {
  return render(
    <SWRConfig
      value={{
        dedupingInterval: 0,
        provider: () => new Map(),
        shouldRetryOnError: false,
      }}
    >
      <AgentDetailPage agentId={agentId} />
    </SWRConfig>,
  );
}

describe("AgentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listControlPlaneAgents).mockResolvedValue({
      agents: [requirementManager],
      total: 1,
    });
    vi.mocked(getAgentPromptConfig).mockResolvedValue({
      company_id: "cmp_projectcell",
      agent_id: "requirement-manager",
      system_prompt: "",
      updated_by: null,
      metadata: {},
      created_at: null,
      updated_at: null,
    });
  });

  it("loads the control-plane definition for built-in runtime agent pages", async () => {
    vi.mocked(getControlPlaneAgent).mockResolvedValue(requirementManager);

    renderDetail("requirement-manager");

    await waitFor(() => {
      expect(getControlPlaneAgent).toHaveBeenCalledWith("requirement-manager");
    });
    expect(
      await screen.findByRole("button", { name: "editAgent" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Requirement extraction")).toBeInTheDocument();
  });
});
