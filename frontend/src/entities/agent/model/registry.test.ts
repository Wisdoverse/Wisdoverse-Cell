import { describe, expect, it } from "vitest";

import {
  AGENT_REGISTRY,
  ORGANIZATION_ROLE_TEMPLATES,
  agentDefinitionToMeta,
  agentDefinitionsToMetas,
  getAllAgents,
} from "./registry";
import type { ControlPlaneAgentDefinition } from "./types";

function controlPlaneAgent(
  overrides: Partial<ControlPlaneAgentDefinition> = {},
): ControlPlaneAgentDefinition {
  return {
    role_id: "role_1",
    company_id: "company_1",
    agent_id: "cto",
    display_name: "CTO",
    agent_kind: "organization_role",
    interaction_mode: "routed",
    role: "cto",
    title: "Chief Technology Officer",
    domain: "engineering",
    reports_to_agent_id: null,
    adapter_type: "http",
    adapter_config: {},
    context_sources: ["control_plane"],
    capabilities: ["Architecture decisions"],
    responsibilities: ["Own technical strategy"],
    subscribed_events: ["work_item.created"],
    published_events: ["architecture.decision-proposed"],
    permissions: [],
    budget_policy_id: null,
    escalation_policy: {},
    status: "active",
    created_by: "test",
    metadata: {},
    created_at: "2026-05-02T00:00:00Z",
    updated_at: "2026-05-02T00:00:00Z",
    ...overrides,
  };
}

describe("agent registry architecture boundary", () => {
  it("keeps built-in runtime services classified as non-organization roles", () => {
    expect(getAllAgents()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "requirement-manager",
          agentKind: "business_runtime_agent",
          interactionMode: "internal",
          runtimeBoundary: "root_agent",
          businessAgent: true,
        }),
        expect.objectContaining({
          id: "chat-agent",
          agentKind: "integration_gateway",
          interactionMode: "direct",
        }),
        expect.objectContaining({
          id: "coordinator",
          agentKind: "system_worker",
          interactionMode: "routed",
        }),
      ]),
    );

    expect(
      Object.values(AGENT_REGISTRY).filter(
        (agent) => agent.agentKind === "organization_role",
      ),
    ).toHaveLength(0);
  });

  it("marks real business runtime agents as root agents", () => {
    const businessAgentIds = getAllAgents()
      .filter((agent) => agent.businessAgent)
      .map((agent) => agent.id)
      .sort();

    expect(businessAgentIds).toEqual([
      "dev-agent",
      "pjm-agent",
      "qa-agent",
      "requirement-manager",
    ]);
    expect(AGENT_REGISTRY["channel-gateway"]).toMatchObject({
      runtimeBoundary: "gateway",
      implemented: true,
      businessAgent: false,
    });
  });

  it("documents event-driven topology for gateway, sync, dev, and QA", () => {
    expect(AGENT_REGISTRY["chat-agent"].downstream).toEqual(
      expect.arrayContaining(["coordinator", "sync-agent"]),
    );
    expect(AGENT_REGISTRY["sync-agent"].upstream).toContain("chat-agent");
    expect(AGENT_REGISTRY["qa-agent"].upstream).toEqual(
      expect.arrayContaining(["dev-agent", "coordinator"]),
    );
    expect(AGENT_REGISTRY["chat-agent"].publishedEvents).toEqual(
      expect.arrayContaining(["coordinator.command", "sync.trigger"]),
    );
    expect(AGENT_REGISTRY.coordinator.publishedEvents).toEqual(
      expect.arrayContaining(["pm.tasks-ready-for-dev", "qa.run-requested"]),
    );
    expect(AGENT_REGISTRY["dev-agent"].publishedEvents).toContain("qa.run-requested");
    expect(AGENT_REGISTRY["qa-agent"].subscribedEvents).toContain("qa.run-requested");
  });

  it("maps control-plane records into manageable organization-role agents", () => {
    const meta = agentDefinitionToMeta(controlPlaneAgent());

    expect(meta).toMatchObject({
      id: "cto",
      name: "CTO",
      agentKind: "organization_role",
      interactionMode: "routed",
      source: "control-plane",
      businessAgent: true,
      implemented: true,
      role: "cto",
      title: "Chief Technology Officer",
      domain: "engineering",
      capabilities: ["Architecture decisions"],
      subscribedEvents: ["work_item.created"],
      publishedEvents: ["architecture.decision-proposed"],
    });
  });

  it("exposes first-class organization role templates for frontend creation", () => {
    expect(ORGANIZATION_ROLE_TEMPLATES).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          agentId: "ceo",
          agentKind: "organization_role",
          interactionMode: "routed",
        }),
        expect.objectContaining({
          agentId: "cto",
          agentKind: "organization_role",
          interactionMode: "routed",
        }),
        expect.objectContaining({
          agentId: "cpo",
          agentKind: "organization_role",
          interactionMode: "routed",
        }),
        expect.objectContaining({
          agentId: "coo",
          agentKind: "organization_role",
          interactionMode: "routed",
        }),
      ]),
    );
  });

  it("derives reporting links between control-plane role agents", () => {
    const ceo = controlPlaneAgent({
      role_id: "role_ceo",
      agent_id: "ceo",
      display_name: "CEO",
      role: "ceo",
      title: "Chief Executive Officer",
      domain: "business",
    });
    const cto = controlPlaneAgent({
      role_id: "role_cto",
      agent_id: "cto",
      display_name: "CTO",
      reports_to_agent_id: "ceo",
    });

    expect(agentDefinitionsToMetas([ceo, cto])).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "ceo",
          downstream: ["cto"],
        }),
        expect.objectContaining({
          id: "cto",
          upstream: ["ceo"],
        }),
      ]),
    );
  });
});
