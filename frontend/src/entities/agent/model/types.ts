export type AgentStatus = "running" | "idle" | "warning" | "error" | "stopped";

export type AgentDomain =
  | "product"
  | "engineering"
  | "quality"
  | "operations"
  | "business"
  | "market-sales"
  | "data-ai";

export type ApprovalType = "finance" | "legal" | "technical" | "customer";

export type AgentTabId =
  | "overview"
  | "tasks"
  | "events"
  | "connections"
  | "config"
  | "logs";

export interface AgentMeta {
  id: string;
  name: string;
  shortName: string;
  domain: AgentDomain;
  icon: string;
  description: string;
  tabs: AgentTabId[];
  role?: string;
  title?: string;
  adapterType?: string;
  reportsTo?: string;
  capabilities?: string[];
  source?: "builtin" | "control-plane";
  customWidgets?: string[];
  approvalTypes?: ApprovalType[];
  upstream: string[];
  downstream: string[];
}

export interface AgentRuntimeStatus {
  agent_id: string;
  status: AgentStatus;
  health: number;
  task_count: number;
  pending_count: number;
  error_count: number;
  uptime_seconds: number;
  last_active_at: string;
}

export interface AgentListResponse {
  agents: AgentRuntimeStatus[];
  total: number;
}

export interface ControlPlaneAgentDefinition {
  role_id: string;
  company_id: string;
  agent_id: string;
  display_name: string;
  role: string;
  title: string;
  domain: string;
  reports_to_agent_id: string | null;
  adapter_type: string;
  adapter_config: Record<string, unknown>;
  capabilities: string[];
  responsibilities: string[];
  permissions: string[];
  budget_policy_id: string | null;
  escalation_policy: Record<string, unknown>;
  status: string;
  created_by: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ControlPlaneAgentListResponse {
  agents: ControlPlaneAgentDefinition[];
  total: number;
}

export interface CreateControlPlaneAgentRequest {
  agent_id: string;
  display_name: string;
  role: string;
  title?: string;
  domain: AgentDomain;
  reports_to_agent_id?: string | null;
  adapter_type: string;
  adapter_config?: Record<string, unknown>;
  capabilities?: string[];
  responsibilities?: string[];
  permissions?: string[];
  created_by?: string;
  metadata?: Record<string, unknown>;
}

export interface WakeControlPlaneAgentRequest {
  input?: Record<string, unknown>;
  actor_id?: string;
  trace_id?: string;
  goal_id?: string;
  work_item_id?: string;
}

export interface WakeControlPlaneAgentResponse {
  run: {
    run_id: string;
    status: string;
    trace_id: string | null;
    agent_id: string;
  } & Record<string, unknown>;
  output: Record<string, unknown>;
}
