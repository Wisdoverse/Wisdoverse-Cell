import { apiClient } from "@/lib/api/client";

import type {
  ControlPlaneApprovalListResponse,
  ControlPlaneArtifactListResponse,
  ControlPlaneBudgetPolicy,
  ControlPlaneBudgetPolicyListResponse,
  ControlPlaneBudgetUsageListResponse,
  ControlPlaneDecisionListResponse,
  ControlPlaneEvolutionProposalListResponse,
  ControlPlaneGoalListResponse,
  ControlPlaneRunListResponse,
  ControlPlaneTimelineResponse,
  ControlPlaneWorkItemListResponse,
  BudgetPeriod,
  BudgetPolicyStatus,
  BudgetScope,
  EvolutionApprovalState,
  EvolutionRolloutState,
  EvolutionTier,
} from "../model/types";

export interface ControlPlaneGoalFilters {
  status?: string;
  owner_agent_id?: string;
  owner_user_id?: string;
  search?: string;
  limit?: number;
}

export interface ControlPlaneGoalCreateRequest {
  company_id?: string;
  title: string;
  description?: string;
  status?: string;
  owner_agent_id?: string;
  owner_user_id?: string;
  success_metric?: string;
  target_value?: number;
  current_value?: number;
  tags?: string[];
  created_by?: string;
  metadata?: Record<string, unknown>;
}

export interface ControlPlaneWorkItemFilters {
  status?: string;
  priority?: string;
  goal_id?: string;
  owner_agent_id?: string;
  owner_user_id?: string;
  search?: string;
  limit?: number;
}

export interface ControlPlaneWorkItemCreateRequest {
  company_id?: string;
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  goal_id?: string;
  owner_agent_id?: string;
  owner_user_id?: string;
  source?: string;
  external_ref?: string;
  dependencies?: string[];
  approval_required?: boolean;
  created_by?: string;
  metadata?: Record<string, unknown>;
}

export interface ControlPlaneRunFilters {
  status?: string;
  agent_id?: string;
  trace_id?: string;
  goal_id?: string;
  work_item_id?: string;
  limit?: number;
}

export interface ControlPlaneEvidenceFilters {
  status?: string;
  run_id?: string;
  trace_id?: string;
  goal_id?: string;
  work_item_id?: string;
  limit?: number;
}

export interface ControlPlaneArtifactFilters {
  artifact_type?: string;
  run_id?: string;
  goal_id?: string;
  work_item_id?: string;
  created_by_agent_id?: string;
  limit?: number;
}

export interface ControlPlaneEvolutionProposalFilters {
  tier?: EvolutionTier;
  approval_state?: EvolutionApprovalState;
  rollout_state?: EvolutionRolloutState;
  scope?: string;
  limit?: number;
}

export interface ControlPlaneBudgetPolicyFilters {
  scope?: BudgetScope;
  scope_id?: string;
  period?: BudgetPeriod;
  status?: BudgetPolicyStatus;
  limit?: number;
}

export interface ControlPlaneBudgetPolicyCreateRequest {
  company_id?: string;
  scope: BudgetScope;
  period: BudgetPeriod;
  limit_usd: number;
  scope_id?: string;
  warning_threshold?: number;
  status?: BudgetPolicyStatus;
  model_allowlist?: string[];
  created_by?: string;
  metadata?: Record<string, unknown>;
}

export interface ControlPlaneBudgetPolicyUpdateRequest {
  limit_usd?: number;
  warning_threshold?: number;
  status?: BudgetPolicyStatus;
  model_allowlist?: string[];
  actor_id?: string;
  metadata?: Record<string, unknown>;
}

export interface ControlPlaneApprovalActionRequest {
  resolved_by?: string;
}

export function listControlPlaneGoals(
  filters?: ControlPlaneGoalFilters,
): Promise<ControlPlaneGoalListResponse> {
  return apiClient.get<ControlPlaneGoalListResponse>(
    "/control-plane/goals",
    filters,
  );
}

export function createControlPlaneGoal(
  payload: ControlPlaneGoalCreateRequest,
): Promise<ControlPlaneGoalListResponse["goals"][number]> {
  return apiClient.post<ControlPlaneGoalListResponse["goals"][number]>(
    "/control-plane/goals",
    payload,
  );
}

export function listControlPlaneWorkItems(
  filters?: ControlPlaneWorkItemFilters,
): Promise<ControlPlaneWorkItemListResponse> {
  return apiClient.get<ControlPlaneWorkItemListResponse>(
    "/control-plane/work-items",
    filters,
  );
}

export function createControlPlaneWorkItem(
  payload: ControlPlaneWorkItemCreateRequest,
): Promise<ControlPlaneWorkItemListResponse["work_items"][number]> {
  return apiClient.post<ControlPlaneWorkItemListResponse["work_items"][number]>(
    "/control-plane/work-items",
    payload,
  );
}

export function listControlPlaneRuns(
  filters?: ControlPlaneRunFilters,
): Promise<ControlPlaneRunListResponse> {
  return apiClient.get<ControlPlaneRunListResponse>(
    "/control-plane/runs",
    filters,
  );
}

export function listControlPlaneDecisions(
  filters?: ControlPlaneEvidenceFilters,
): Promise<ControlPlaneDecisionListResponse> {
  return apiClient.get<ControlPlaneDecisionListResponse>(
    "/control-plane/decisions",
    filters,
  );
}

export function listControlPlaneArtifacts(
  filters?: ControlPlaneArtifactFilters,
): Promise<ControlPlaneArtifactListResponse> {
  return apiClient.get<ControlPlaneArtifactListResponse>(
    "/control-plane/artifacts",
    filters,
  );
}

export function listControlPlaneEvolutionProposals(
  filters?: ControlPlaneEvolutionProposalFilters,
): Promise<ControlPlaneEvolutionProposalListResponse> {
  return apiClient.get<ControlPlaneEvolutionProposalListResponse>(
    "/control-plane/evolution-proposals",
    filters,
  );
}

export function listControlPlaneApprovals(
  filters?: Pick<
    ControlPlaneEvidenceFilters,
    "status" | "run_id" | "trace_id" | "limit"
  >,
): Promise<ControlPlaneApprovalListResponse> {
  return apiClient.get<ControlPlaneApprovalListResponse>(
    "/control-plane/approvals",
    filters,
  );
}

export function approveControlPlaneApproval(
  approvalId: string,
  payload: ControlPlaneApprovalActionRequest = {},
): Promise<Record<string, unknown>> {
  return apiClient.post<Record<string, unknown>>(
    `/control-plane/approvals/${approvalId}/approve`,
    payload,
  );
}

export function rejectControlPlaneApproval(
  approvalId: string,
  payload: ControlPlaneApprovalActionRequest = {},
): Promise<Record<string, unknown>> {
  return apiClient.post<Record<string, unknown>>(
    `/control-plane/approvals/${approvalId}/reject`,
    payload,
  );
}

export function listControlPlaneBudgetPolicies(
  filters?: ControlPlaneBudgetPolicyFilters,
): Promise<ControlPlaneBudgetPolicyListResponse> {
  return apiClient.get<ControlPlaneBudgetPolicyListResponse>(
    "/control-plane/budgets/policies",
    filters,
  );
}

export function createControlPlaneBudgetPolicy(
  payload: ControlPlaneBudgetPolicyCreateRequest,
): Promise<ControlPlaneBudgetPolicy> {
  return apiClient.post<ControlPlaneBudgetPolicy>(
    "/control-plane/budgets/policies",
    payload,
  );
}

export function updateControlPlaneBudgetPolicy(
  budgetId: string,
  payload: ControlPlaneBudgetPolicyUpdateRequest,
): Promise<ControlPlaneBudgetPolicy> {
  return apiClient.patch<ControlPlaneBudgetPolicy>(
    `/control-plane/budgets/policies/${budgetId}`,
    payload,
  );
}

export function listControlPlaneBudgetUsage(
  filters?: Pick<ControlPlaneEvidenceFilters, "run_id" | "trace_id" | "limit"> & {
    budget_id?: string;
  },
): Promise<ControlPlaneBudgetUsageListResponse> {
  return apiClient.get<ControlPlaneBudgetUsageListResponse>(
    "/control-plane/budgets/usage",
    filters,
  );
}

export function getControlPlaneTimeline(filters: {
  run_id?: string;
  trace_id?: string;
  limit?: number;
}): Promise<ControlPlaneTimelineResponse> {
  return apiClient.get<ControlPlaneTimelineResponse>(
    "/control-plane/timeline",
    filters,
  );
}
