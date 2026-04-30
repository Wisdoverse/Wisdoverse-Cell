import type { AgentMeta, AgentDomain } from "@/lib/api/types";

export const AGENT_REGISTRY: Record<string, AgentMeta> = {
  "requirement-manager": {
    id: "requirement-manager",
    name: "Requirement Manager",
    shortName: "RM",
    domain: "product",
    icon: "ClipboardList",
    description: "Extracts and manages product requirements from various input sources",
    tabs: ["overview", "tasks", "events", "connections", "config", "logs"],
    customWidgets: ["rm-requirements", "rm-ingest", "rm-questions"],
    approvalTypes: ["technical"],
    upstream: [],
    downstream: [],
  },
  // Future agents will be added here as they come online.
  // Each agent only needs a single entry in this registry
  // for the UI to auto-generate its Fleet card and Spoke detail page.
};

export function getAgentMeta(agentId: string): AgentMeta {
  const meta = AGENT_REGISTRY[agentId];
  if (!meta) throw new Error(`Unknown agent: ${agentId}`);
  return meta;
}

export function getAgentsByDomain(domain: AgentDomain): AgentMeta[] {
  return Object.values(AGENT_REGISTRY).filter((a) => a.domain === domain);
}

export function getAllAgents(): AgentMeta[] {
  return Object.values(AGENT_REGISTRY);
}
