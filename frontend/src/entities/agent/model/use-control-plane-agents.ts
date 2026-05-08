import useSWR from "swr";

import {
  getAgentPromptConfig,
  getControlPlaneAgent,
  listControlPlaneAgents,
} from "../api/control-plane-agents";
import type { AgentPromptConfig, ControlPlaneAgentListResponse } from "./types";

export function useControlPlaneAgents(filters?: {
  status?: string;
  adapter_type?: string;
  search?: string;
  limit?: number;
}) {
  return useSWR<ControlPlaneAgentListResponse>(
    ["control-plane-agents", filters],
    () => listControlPlaneAgents(filters),
  );
}

export function useControlPlaneAgent(agentId: string | undefined) {
  return useSWR(
    agentId ? ["control-plane-agent", agentId] : null,
    () => getControlPlaneAgent(agentId!),
  );
}

export function useAgentPromptConfig(agentId: string | undefined) {
  return useSWR<AgentPromptConfig>(
    agentId ? ["agent-prompt-config", agentId] : null,
    () => getAgentPromptConfig(agentId!),
  );
}
