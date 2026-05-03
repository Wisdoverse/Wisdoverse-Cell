import useSWR from "swr";

import { getAgentStatus, getAgents } from "@/lib/api/agents";
import type { AgentListResponse, AgentRuntimeStatus } from "@/lib/api/types";

export function useAgents(filters?: {
  status?: string;
  domain?: string;
  search?: string;
}) {
  return useSWR<AgentListResponse>(
    ["agents", filters],
    () => getAgents(filters),
    { refreshInterval: 30000 },
  );
}

export function useAgentDetail(agentId: string | undefined) {
  return useSWR<AgentRuntimeStatus>(
    agentId ? ["agent-detail", agentId] : null,
    () => getAgentStatus(agentId!),
    { refreshInterval: 10000 },
  );
}
