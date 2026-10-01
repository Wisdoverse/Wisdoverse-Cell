import { apiClient } from "@/lib/api/client";

export type ExecutionControlAction = "pause" | "resume" | "terminate";

export interface ExecutionControlResponse {
  run_id: string;
  requested_action: ExecutionControlAction;
  state: "requested" | string;
}

export interface ExecutionRecoveryResponse {
  run_id: string;
  state: string;
  handoff: string;
}

export function requestExecutionControl(
  runId: string,
  payload: { company_id: string; action: ExecutionControlAction; reason: string },
) {
  return apiClient.post<ExecutionControlResponse>(`/control-plane/executions/${runId}/control`, payload);
}

export function recoverAbandonedExecution(
  runId: string,
  payload: { company_id: string; reason: string; effects_reconciled: true },
) {
  return apiClient.post<ExecutionRecoveryResponse>(`/control-plane/executions/${runId}/recover`, payload);
}
