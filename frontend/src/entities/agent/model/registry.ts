import type {
  AgentDomain,
  AgentMeta,
  ControlPlaneAgentDefinition,
  OrganizationRoleTemplate,
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

export const ORGANIZATION_ROLE_TEMPLATES: OrganizationRoleTemplate[] = [
  {
    agentId: "ceo",
    displayName: "CEO",
    role: "ceo",
    title: "Chief Executive Officer",
    domain: "business",
    agentKind: "organization_role",
    interactionMode: "routed",
  },
  {
    agentId: "cto",
    displayName: "CTO",
    role: "cto",
    title: "Chief Technology Officer",
    domain: "engineering",
    agentKind: "organization_role",
    interactionMode: "routed",
  },
  {
    agentId: "cpo",
    displayName: "CPO",
    role: "cpo",
    title: "Chief Product Officer",
    domain: "product",
    agentKind: "organization_role",
    interactionMode: "routed",
  },
  {
    agentId: "coo",
    displayName: "COO",
    role: "coo",
    title: "Chief Operating Officer",
    domain: "operations",
    agentKind: "organization_role",
    interactionMode: "routed",
  },
];

export const AGENT_REGISTRY: Record<string, AgentMeta> = {
  "requirement-manager": {
    id: "requirement-manager",
    name: "Requirement Manager",
    shortName: "RM",
    domain: "product",
    icon: "ClipboardList",
    description: "Extracts, confirms, and manages requirements from input sources",
    tabs: ["overview", "tasks", "events", "connections", "config", "logs"],
    agentKind: "business_runtime_agent",
    interactionMode: "internal",
    role: "requirement-agent",
    title: "Requirement Manager Agent",
    runtimeBoundary: "root_agent",
    implemented: true,
    businessAgent: true,
    contextSources: ["feishu", "manual_upload", "control_plane"],
    subscribedEvents: [
      "project.created",
      "project.updated",
      "sprint.started",
      "sprint.completed",
      "meeting.uploaded",
      "coordinator.dispatch",
    ],
    publishedEvents: [
      "requirement.extracted",
      "requirement.confirmed",
      "requirement.rejected",
      "requirement.deleted",
    ],
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
    runtimeBoundary: "gateway",
    implemented: true,
    businessAgent: false,
    contextSources: ["feishu", "control_plane"],
    subscribedEvents: ["chat.pm-response", "coordinator.response"],
    publishedEvents: ["chat.pm-query", "coordinator.command", "sync.trigger"],
    upstream: [],
    downstream: ["coordinator", "sync-agent"],
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
    runtimeBoundary: "orchestration",
    implemented: true,
    businessAgent: false,
    contextSources: ["event_bus", "scratchpad", "control_plane"],
    subscribedEvents: [
      "coordinator.command",
      "task.notification",
      "task.progress",
      "pm.prd-ready",
      "pm.decompose-completed",
      "pm.decomposition-failed",
      "analysis.risk-detected",
    ],
    publishedEvents: [
      "coordinator.response",
      "coordinator.dispatch",
      "pm.tasks-ready-for-dev",
      "qa.run-requested",
    ],
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
    runtimeBoundary: "capability",
    implemented: true,
    businessAgent: false,
    contextSources: ["openproject", "feishu", "control_plane"],
    subscribedEvents: ["sync.trigger"],
    publishedEvents: [
      "sync.started",
      "sync.completed",
      "sync.failed",
      "sync.task-needs-decompose",
    ],
    upstream: ["chat-agent"],
    downstream: ["pjm-agent", "analysis-agent"],
  },
  "pjm-agent": {
    id: "pjm-agent",
    name: "PJM Agent",
    shortName: "PM",
    domain: "product",
    icon: "GitBranch",
    description: "Task decomposition, approval preparation, alerts, and reports agent",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "business_runtime_agent",
    interactionMode: "internal",
    role: "project-management-agent",
    title: "Project Management Agent",
    runtimeBoundary: "root_agent",
    implemented: true,
    businessAgent: true,
    contextSources: ["openproject", "feishu", "control_plane"],
    subscribedEvents: [
      "sync.completed",
      "analysis.risk-detected",
      "chat.pm-query",
      "sync.task-needs-decompose",
      "coordinator.dispatch",
    ],
    publishedEvents: [
      "pm.alert-triggered",
      "chat.pm-response",
      "pm.decompose-completed",
      "pm.decomposition-failed",
      "pm.approval-timeout",
      "pm.tasks-ready-for-dev",
      "sync.task-needs-decompose",
    ],
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
    runtimeBoundary: "capability",
    implemented: true,
    businessAgent: false,
    contextSources: ["openproject", "control_plane"],
    subscribedEvents: ["sync.completed"],
    publishedEvents: [
      "report.daily-generated",
      "report.weekly-generated",
      "analysis.risk-detected",
      "analysis.quality-evaluated",
    ],
    upstream: ["sync-agent"],
    downstream: ["pjm-agent"],
  },
  "qa-agent": {
    id: "qa-agent",
    name: "QA Agent",
    shortName: "QA",
    domain: "quality",
    icon: "ShieldCheck",
    description: "Automated acceptance and quality verification agent",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "business_runtime_agent",
    interactionMode: "internal",
    role: "quality-agent",
    title: "QA Agent",
    runtimeBoundary: "root_agent",
    implemented: true,
    businessAgent: true,
    contextSources: ["gitlab", "control_plane"],
    subscribedEvents: ["code.committed", "qa.run-requested"],
    publishedEvents: ["qa.acceptance-completed", "qa.gate-failed"],
    upstream: ["dev-agent", "coordinator"],
    downstream: [],
  },
  "dev-agent": {
    id: "dev-agent",
    name: "Dev Agent",
    shortName: "DA",
    domain: "engineering",
    icon: "Code",
    description: "AgentForge-backed software delivery execution agent",
    tabs: DEFAULT_AGENT_TABS,
    agentKind: "business_runtime_agent",
    interactionMode: "internal",
    role: "development-agent",
    title: "Development Agent",
    runtimeBoundary: "root_agent",
    implemented: true,
    businessAgent: true,
    contextSources: ["agentforge", "gitlab", "control_plane"],
    subscribedEvents: ["pm.tasks-ready-for-dev", "qa.acceptance-completed"],
    publishedEvents: [
      "dev.workflow-created",
      "dev.mr-created",
      "dev.task-completed",
      "dev.task-failed",
      "qa.run-requested",
    ],
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
    runtimeBoundary: "capability",
    implemented: true,
    businessAgent: false,
    contextSources: ["traces", "control_plane"],
    subscribedEvents: [
      "evolution.cycle-triggered",
      "evolution.human-feedback",
      "evolution.pattern-approved",
    ],
    publishedEvents: ["evolution.skill-proposed", "evolution.pattern-proposed"],
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
    runtimeBoundary: "gateway",
    implemented: true,
    businessAgent: false,
    contextSources: ["feishu", "wecom", "control_plane"],
    subscribedEvents: ["channel.message.outbound"],
    publishedEvents: [
      "channel.message.inbound",
      "channel.message.delivered",
      "channel.adapter.status",
    ],
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
    subscribedEvents: agent.subscribed_events ?? [],
    publishedEvents: agent.published_events ?? [],
    source: "control-plane",
    implemented: true,
    businessAgent:
      agent.agent_kind === "organization_role" ||
      agent.agent_kind === "business_runtime_agent",
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
