import { apiClient } from "./client";
import type { BatchOperationResponse, Requirement } from "./types";

export function confirmRequirement(
  id: string,
  confirmedBy: string,
): Promise<Requirement> {
  return apiClient.put<Requirement>(`/requirements/${id}/confirm`, {
    confirmed_by: confirmedBy,
  });
}

export function rejectRequirement(
  id: string,
  reason: string,
  rejectedBy?: string,
): Promise<Requirement> {
  return apiClient.put<Requirement>(`/requirements/${id}/reject`, {
    reason,
    rejected_by: rejectedBy,
  });
}

export function batchConfirm(ids: string[]): Promise<BatchOperationResponse> {
  return apiClient.post<BatchOperationResponse>(
    "/requirements/batch/confirm",
    { ids },
  );
}

export function batchReject(
  ids: string[],
  reason: string,
): Promise<BatchOperationResponse> {
  return apiClient.post<BatchOperationResponse>(
    "/requirements/batch/reject",
    { ids, reason },
  );
}
