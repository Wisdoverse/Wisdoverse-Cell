import { apiClient } from "@/lib/api/client";

import type {
  ControlPlaneApprovalListResponse,
  ControlPlaneArtifactListResponse,
  ControlPlaneBudgetUsageListResponse,
  ControlPlaneDecisionListResponse,
  ControlPlaneEvolutionProposalListResponse,
  ControlPlaneGoalListResponse,
  ControlPlaneRunListResponse,
  ControlPlaneTimelineResponse,
  ControlPlaneWorkItemListResponse,
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

export interface ControlPlaneWorkItemFilters {
  status?: string;
  priority?: string;
  goal_id?: string;
  owner_agent_id?: string;
  owner_user_id?: string;
  search?: string;
  limit?: number;
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

export function listControlPlaneWorkItems(
  filters?: ControlPlaneWorkItemFilters,
): Promise<ControlPlaneWorkItemListResponse> {
  return apiClient.get<ControlPlaneWorkItemListResponse>(
    "/control-plane/work-items",
    filters,
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
