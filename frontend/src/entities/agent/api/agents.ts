import { apiClient } from "@/lib/api/client";

import type { AgentListResponse, AgentRuntimeStatus } from "../model/types";

export function getAgents(filters?: {
  status?: string;
  domain?: string;
  search?: string;
}): Promise<AgentListResponse> {
  return apiClient.get<AgentListResponse>("/agents", filters);
}

export function getAgentStatus(agentId: string): Promise<AgentRuntimeStatus> {
  return apiClient.get<AgentRuntimeStatus>(`/agents/${agentId}/status`);
}
