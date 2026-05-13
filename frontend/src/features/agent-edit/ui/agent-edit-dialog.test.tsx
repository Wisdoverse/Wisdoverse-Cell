import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import type { ControlPlaneAgentDefinition } from "@/entities/agent";
import { AgentEditDialog } from "./agent-edit-dialog";

beforeAll(() => {
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
});

const agent: ControlPlaneAgentDefinition = {
  role_id: "role_cto",
  company_id: "default",
  agent_id: "cto",
  display_name: "CTO",
  agent_kind: "organization_role",
  interaction_mode: "routed",
  role: "cto",
  title: "Chief Technology Officer",
  domain: "engineering",
  reports_to_agent_id: null,
  adapter_type: "http",
  adapter_config: {
    base_url: "https://agents.internal",
    path: "/cto/request",
  },
  context_sources: ["control_plane"],
  capabilities: ["architecture"],
  responsibilities: ["own technical strategy"],
  subscribed_events: ["work_item.created"],
  published_events: ["architecture.decision-proposed"],
  permissions: [],
  budget_policy_id: null,
  escalation_policy: {},
  status: "active",
  created_by: "seed",
  metadata: {},
  created_at: "2026-05-08T00:00:00Z",
  updated_at: "2026-05-08T00:00:00Z",
};

describe("AgentEditDialog", () => {
  it("opens with the current control-plane agent definition", async () => {
    const user = userEvent.setup();

    render(
      <AgentEditDialog
        agent={agent}
        availableAgents={[
          {
            id: "ceo",
            name: "CEO",
            shortName: "CEO",
            domain: "business",
            icon: "Bot",
            description: "Chief Executive Officer",
            tabs: ["overview", "config"],
            upstream: [],
            downstream: ["cto"],
          },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "editAgent" }));
    expect(screen.getByText("operatorBasics")).toBeInTheDocument();
    expect(screen.getByLabelText("capabilities")).toHaveValue("architecture");
    await user.click(screen.getByRole("button", { name: "showAdvanced" }));

    expect(screen.getByLabelText("agentName")).toHaveValue("CTO");
    expect(screen.getByLabelText("agentId")).toHaveValue("cto");
    expect(screen.getByLabelText("titleField")).toHaveValue("Chief Technology Officer");
    expect(screen.getByLabelText("baseUrl")).toHaveValue("https://agents.internal");
  });
});
