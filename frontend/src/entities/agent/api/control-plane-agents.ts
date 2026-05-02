import { apiClient } from "@/lib/api/client";
import type {
  ControlPlaneAgentDefinition,
  ControlPlaneAgentListResponse,
  CreateControlPlaneAgentRequest,
  WakeControlPlaneAgentRequest,
  WakeControlPlaneAgentResponse,
} from "../model/types";

export function listControlPlaneAgents(filters?: {
  status?: string;
  agent_kind?: string;
  interaction_mode?: string;
  adapter_type?: string;
  search?: string;
  limit?: number;
}): Promise<ControlPlaneAgentListResponse> {
  return apiClient.get<ControlPlaneAgentListResponse>(
    "/control-plane/agents",
    filters,
  );
}

export function getControlPlaneAgent(
  agentId: string,
): Promise<ControlPlaneAgentDefinition> {
  return apiClient.get<ControlPlaneAgentDefinition>(
    `/control-plane/agents/${agentId}`,
  );
}

export function createControlPlaneAgent(
  payload: CreateControlPlaneAgentRequest,
): Promise<ControlPlaneAgentDefinition> {
  return apiClient.post<ControlPlaneAgentDefinition>(
    "/control-plane/agents",
    payload,
  );
}

export function updateControlPlaneAgentStatus(
  agentId: string,
  payload: { status: string; actor_id?: string },
): Promise<ControlPlaneAgentDefinition> {
  return apiClient.patch<ControlPlaneAgentDefinition>(
    `/control-plane/agents/${agentId}/status`,
    payload,
  );
}

export function wakeControlPlaneAgent(
  agentId: string,
  payload: WakeControlPlaneAgentRequest = {},
): Promise<WakeControlPlaneAgentResponse> {
  return apiClient.post<WakeControlPlaneAgentResponse>(
    `/control-plane/agents/${agentId}/wake`,
    payload,
  );
}
