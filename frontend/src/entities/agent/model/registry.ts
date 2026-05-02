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
    name: "Requirements Module",
    shortName: "RM",
    domain: "product",
    icon: "ClipboardList",
    description: "Extracts, confirms, and manages requirements from input sources",
    tabs: ["overview", "tasks", "events", "connections", "config", "logs"],
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "requirement-capability",
    title: "Requirements Capability",
    contextSources: ["feishu", "manual_upload", "control_plane"],
    customWidgets: ["rm-requirements", "rm-ingest", "rm-questions"],
    approvalTypes: ["technical"],
    upstream: [],
    downstream: [],
  },
  "chat-agent": {
    id: "chat-agent",
    name: "User Gateway",
    shortName: "CA",
    domain: "operations",
    icon: "MessageSquare",
    description: "Direct user interaction and routing surface",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "integration_gateway",
    interactionMode: "direct",
    role: "reception",
    title: "User Interaction Gateway",
    contextSources: ["feishu", "control_plane"],
    upstream: [],
    downstream: ["coordinator"],
  },
  coordinator: {
    id: "coordinator",
    name: "Coordinator Worker",
    shortName: "CO",
    domain: "operations",
    icon: "Network",
    description: "Cross-module event router and decision synthesizer",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "system_worker",
    interactionMode: "routed",
    role: "orchestrator",
    title: "Coordination Engine",
    contextSources: ["event_bus", "scratchpad", "control_plane"],
    upstream: ["chat-agent"],
    downstream: ["pjm-agent", "dev-agent", "qa-agent"],
  },
  "sync-agent": {
    id: "sync-agent",
    name: "Sync Module",
    shortName: "SA",
    domain: "operations",
    icon: "RefreshCcw",
    description: "OpenProject and Feishu synchronization capability",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "sync-capability",
    title: "Context Sync Capability",
    contextSources: ["openproject", "feishu", "control_plane"],
    upstream: [],
    downstream: ["pjm-agent", "analysis-agent"],
  },
  "pjm-agent": {
    id: "pjm-agent",
    name: "Project Module",
    shortName: "PM",
    domain: "product",
    icon: "GitBranch",
    description: "Task decomposition, approval preparation, alerts, and reports capability",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "project-management-capability",
    title: "Project Management Capability",
    contextSources: ["openproject", "feishu", "control_plane"],
    upstream: ["sync-agent", "coordinator"],
    downstream: ["dev-agent", "qa-agent"],
  },
  "analysis-agent": {
    id: "analysis-agent",
    name: "Analysis Module",
    shortName: "AA",
    domain: "data-ai",
    icon: "ChartNoAxesCombined",
    description: "Risk detection and operating analytics capability",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "analysis-capability",
    title: "Analysis Capability",
    contextSources: ["openproject", "control_plane"],
    upstream: ["sync-agent"],
    downstream: ["pjm-agent"],
  },
  "qa-agent": {
    id: "qa-agent",
    name: "Quality Module",
    shortName: "QA",
    domain: "quality",
    icon: "ShieldCheck",
    description: "Automated acceptance and quality verification capability",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "quality-capability",
    title: "Quality Capability",
    contextSources: ["gitlab", "control_plane"],
    upstream: ["dev-agent"],
    downstream: [],
  },
  "dev-agent": {
    id: "dev-agent",
    name: "Development Module",
    shortName: "DA",
    domain: "engineering",
    icon: "Code",
    description: "AgentForge-backed software delivery execution module",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "development-capability",
    title: "Development Capability",
    contextSources: ["agentforge", "gitlab", "control_plane"],
    upstream: ["pjm-agent", "coordinator"],
    downstream: ["qa-agent"],
  },
  "evolution-agent": {
    id: "evolution-agent",
    name: "Evolution Module",
    shortName: "EA",
    domain: "data-ai",
    icon: "Sparkles",
    description: "Self-evolution proposal and system improvement analyzer",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "capability_module",
    interactionMode: "internal",
    role: "evolution-capability",
    title: "Evolution Capability",
    contextSources: ["traces", "control_plane"],
    upstream: [],
    downstream: [],
  },
  "channel-gateway": {
    id: "channel-gateway",
    name: "Channel Gateway",
    shortName: "CG",
    domain: "operations",
    icon: "RadioTower",
    description: "Multi-channel inbound and outbound messaging boundary",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "integration_gateway",
    interactionMode: "direct",
    role: "channel-gateway",
    title: "Channel Integration Gateway",
    contextSources: ["feishu", "wecom", "control_plane"],
    upstream: [],
    downstream: ["chat-agent"],
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
    agentKind: agent.agent_kind,
    interactionMode: agent.interaction_mode,
    adapterType: agent.adapter_type,
    reportsTo: agent.reports_to_agent_id ?? undefined,
    contextSources: agent.context_sources,
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
