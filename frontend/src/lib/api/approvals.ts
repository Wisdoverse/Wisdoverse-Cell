import { apiClient } from "./client";
import type { ApprovalListResponse } from "./types";

export function getApprovals(filters?: {
  type?: string;
  status?: string;
}): Promise<ApprovalListResponse> {
  return apiClient.get<ApprovalListResponse>("/approvals", filters);
}

export function approveRequest(id: string): Promise<void> {
  return apiClient.post<void>(`/approvals/${id}/approve`, {});
}

export function rejectRequest(
  id: string,
  reason?: string,
): Promise<void> {
  return apiClient.post<void>(`/approvals/${id}/reject`, { reason });
}
