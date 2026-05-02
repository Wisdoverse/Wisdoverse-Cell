import type {
  AgentDomain,
  AgentMeta,
  ControlPlaneAgentDefinition,
} from "./types";

const DEFAULT_AGENT_TABS: AgentMeta["tabs"] = [
  "overview",
  "tasks",
  "events",
  "connections",
  "config",
  "logs",
];

const AGENT_DOMAINS: AgentDomain[] = [
  "product",
  "engineering",
  "quality",
  "operations",
  "business",
  "market-sales",
  "data-ai",
];

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
};

export function getAgentMeta(agentId: string): AgentMeta {
  const meta = AGENT_REGISTRY[agentId];
  if (!meta) throw new Error(`Unknown agent: ${agentId}`);
  return meta;
}

export function getAgentsByDomain(domain: AgentDomain): AgentMeta[] {
  return Object.values(AGENT_REGISTRY).filter((agent) => agent.domain === domain);
}

export function getAllAgents(): AgentMeta[] {
  return Object.values(AGENT_REGISTRY);
}

export function isAgentDomain(value: string | undefined): value is AgentDomain {
  return AGENT_DOMAINS.includes(value as AgentDomain);
}

export function normalizeAgentDomain(value: string | undefined): AgentDomain {
  return isAgentDomain(value) ? value : "operations";
}

export function agentDefinitionToMeta(
  agent: ControlPlaneAgentDefinition,
  downstream: string[] = [],
): AgentMeta {
  const capabilities = agent.capabilities.length
    ? agent.capabilities
    : agent.responsibilities;
  const shortName = agent.display_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return {
    id: agent.agent_id,
    name: agent.display_name,
    shortName: shortName || agent.agent_id.slice(0, 2).toUpperCase(),
    domain: normalizeAgentDomain(agent.domain),
    icon: "Bot",
    description: capabilities[0] || agent.title || agent.role,
    tabs: DEFAULT_AGENT_TABS,
    role: agent.role,
    title: agent.title,
    adapterType: agent.adapter_type,
    reportsTo: agent.reports_to_agent_id ?? undefined,
    capabilities,
    source: "control-plane",
    upstream: agent.reports_to_agent_id ? [agent.reports_to_agent_id] : [],
    downstream,
  };
}

export function agentDefinitionsToMetas(
  agents: ControlPlaneAgentDefinition[],
): AgentMeta[] {
  const downstreamByAgent = new Map<string, string[]>();
  for (const agent of agents) {
    if (!agent.reports_to_agent_id) continue;
    const downstream = downstreamByAgent.get(agent.reports_to_agent_id) ?? [];
    downstream.push(agent.agent_id);
    downstreamByAgent.set(agent.reports_to_agent_id, downstream);
  }
  return agents.map((agent) =>
    agentDefinitionToMeta(agent, downstreamByAgent.get(agent.agent_id) ?? []),
  );
}
