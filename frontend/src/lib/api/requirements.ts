import { apiClient } from "./client";
import type {
  ConflictCheckRequest,
  ConflictCheckResponse,
  HistoryEntry,
  MessageSearchResult,
  Requirement,
  RequirementFilters,
  RequirementListResponse,
  RequirementUpdateRequest,
  SemanticSearchResponse,
  SimilarRequirement,
} from "./types";

export function listRequirements(
  params: RequirementFilters = {},
): Promise<RequirementListResponse> {
  return apiClient.get<RequirementListResponse>("/requirements", params);
}

export function getRequirement(id: string): Promise<Requirement> {
  return apiClient.get<Requirement>(`/requirements/${id}`);
}

export function updateRequirement(
  id: string,
  data: RequirementUpdateRequest,
): Promise<Requirement> {
  return apiClient.put<Requirement>(`/requirements/${id}`, data);
}

export function deleteRequirement(id: string): Promise<void> {
  return apiClient.delete<void>(`/requirements/${id}`);
}

export function searchRequirements(
  query: string,
  limit?: number,
): Promise<SemanticSearchResponse> {
  return apiClient.get<SemanticSearchResponse>("/requirements/search", {
    q: query,
    limit,
  });
}

export function getSimilarRequirements(
  id: string,
  limit?: number,
): Promise<SimilarRequirement[]> {
  return apiClient.get<SimilarRequirement[]>(`/requirements/${id}/similar`, {
    limit,
  });
}

export function checkConflict(
  data: ConflictCheckRequest,
): Promise<ConflictCheckResponse> {
  return apiClient.post<ConflictCheckResponse>(
    "/requirements/check-conflict",
    data,
  );
}

export function getHistory(id: string): Promise<HistoryEntry[]> {
  return apiClient.get<HistoryEntry[]>(`/requirements/${id}/history`);
}

export function getContext(id: string): Promise<MessageSearchResult[]> {
  return apiClient.get<MessageSearchResult[]>(`/requirements/${id}/context`);
}
