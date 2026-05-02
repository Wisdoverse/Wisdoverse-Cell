import useSWR from "swr";

import {
  getControlPlaneAgent,
  listControlPlaneAgents,
} from "../api/control-plane-agents";
import type { ControlPlaneAgentListResponse } from "./types";

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
