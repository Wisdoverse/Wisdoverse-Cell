import { apiClient } from "./client";
import type { ActivityListResponse } from "./types";

export function getActivity(filters?: {
  agent_id?: string;
  domain?: string;
  limit?: number;
}): Promise<ActivityListResponse> {
  return apiClient.get<ActivityListResponse>("/activity", filters);
}
