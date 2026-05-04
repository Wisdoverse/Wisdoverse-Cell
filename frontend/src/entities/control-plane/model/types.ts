export type GoalStatus = "draft" | "active" | "paused" | "completed" | "cancelled";

export type WorkItemStatus =
  | "queued"
  | "ready"
  | "running"
  | "blocked"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type WorkItemPriority = "low" | "medium" | "high" | "critical";

export type AgentRunStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out";

export type DecisionStatus = "proposed" | "accepted" | "rejected" | "superseded";

export type EvolutionTier = "L1" | "L2" | "L3";

export type EvolutionApprovalState =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "cancelled";

export type EvolutionRolloutState =
  | "proposed"
  | "shadow"
  | "canary"
  | "active"
  | "rolled_back"
  | "rejected";

export type ArtifactType =
  | "prd"
  | "report"
  | "qa_result"
  | "issue"
  | "merge_request"
  | "code_patch"
  | "run_walkthrough"
  | "other";

export type ControlPlaneTimelineType =
  | "audit_event"
  | "agent_run"
  | "approval"
  | "budget_usage"
  | "decision"
  | "artifact";

export interface ControlPlaneGoal {
  goal_id: string;
  company_id: string;
  title: string;
  description: string;
  status: GoalStatus;
  parent_goal_id: string | null;
  owner_agent_id: string | null;
  owner_user_id: string | null;
  success_metric: string;
  target_value: number | null;
  current_value: number | null;
  due_at: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ControlPlaneGoalListResponse {
  goals: ControlPlaneGoal[];
  total: number;
}

export interface ControlPlaneWorkItem {
  work_item_id: string;
  company_id: string;
  title: string;
  description: string;
  status: WorkItemStatus;
  priority: WorkItemPriority;
  goal_id: string | null;
  owner_agent_id: string | null;
  owner_user_id: string | null;
  source: string;
  external_ref: string | null;
  dependencies: string[];
  approval_required: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ControlPlaneWorkItemListResponse {
  work_items: ControlPlaneWorkItem[];
  total: number;
}

export interface ControlPlaneAgentRun {
  run_id: string;
  company_id: string;
  agent_id: string;
  status: AgentRunStatus;
  trace_id: string | null;
  goal_id: string | null;
  work_item_id: string | null;
  trigger_event_id: string | null;
  input_event: Record<string, unknown> | null;
  output_events: Record<string, unknown>[];
  started_at: string;
  completed_at: string | null;
  error_category: string | null;
  error_message: string | null;
  last_successful_step: string | null;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  metadata: Record<string, unknown>;
}

export interface ControlPlaneRunListResponse {
  runs: ControlPlaneAgentRun[];
}

export interface ControlPlaneDecision {
  decision_id: string;
  company_id: string;
  title: string;
  rationale: string;
  status: DecisionStatus;
  run_id: string | null;
  work_item_id: string | null;
  goal_id: string | null;
  options: Record<string, unknown>[];
  selected_option: string | null;
  decided_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ControlPlaneDecisionListResponse {
  decisions: ControlPlaneDecision[];
  total: number;
}

export interface ControlPlaneArtifact {
  artifact_id: string;
  company_id: string;
  artifact_type: ArtifactType;
  title: string;
  uri: string;
  content_hash: string | null;
  run_id: string | null;
  work_item_id: string | null;
  goal_id: string | null;
  created_by_agent_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ControlPlaneArtifactListResponse {
  artifacts: ControlPlaneArtifact[];
  total: number;
}

export interface ControlPlaneEvolutionProposal {
  proposal_id: string;
  company_id: string;
  tier: EvolutionTier;
  scope: string;
  evidence: Record<string, unknown>;
  expected_benefit: string;
  risk: string;
  approval_state: EvolutionApprovalState;
  rollout_state: EvolutionRolloutState;
  approval_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ControlPlaneEvolutionProposalListResponse {
  evolution_proposals: ControlPlaneEvolutionProposal[];
  total: number;
}

export interface ControlPlaneApproval {
  approval_id: string;
  company_id: string;
  category: "finance" | "legal" | "customer" | "technical";
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled";
  requested_by: string;
  source_agent_id: string;
  proposed_action: string;
  reason: string;
  risk: string;
  rollback_note: string;
  affected_resources: string[];
  artifact_links: string[];
  run_id: string | null;
  work_item_id: string | null;
  goal_id: string | null;
  trace_id: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  expires_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ControlPlaneApprovalListResponse {
  approvals: ControlPlaneApproval[];
}

export interface ControlPlaneBudgetUsage {
  usage_id: string;
  company_id: string;
  budget_id: string;
  cost_usd: number;
  model: string;
  input_tokens: number;
  output_tokens: number;
  run_id: string | null;
  trace_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ControlPlaneBudgetUsageListResponse {
  usage: ControlPlaneBudgetUsage[];
}

export interface ControlPlaneAuditEvent {
  audit_event_id: string;
  company_id: string;
  action: string;
  target_type: string;
  target_id: string;
  actor_type: string;
  actor_id: string;
  trace_id: string | null;
  run_id: string | null;
  work_item_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface ControlPlaneTimelineItem {
  type: ControlPlaneTimelineType;
  at: string;
  data: Record<string, unknown>;
}

export interface ControlPlaneTimelineResponse {
  timeline: ControlPlaneTimelineItem[];
}

export interface ControlPlaneWorkbenchSummary {
  goalCount: number;
  openWorkCount: number;
  pendingApprovalCount: number;
  costUsd: number;
}
