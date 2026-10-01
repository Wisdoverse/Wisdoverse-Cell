import { apiClient } from "@/lib/api/client";

export interface EvaluationReport {
  evaluation_report_id: string;
  proposal_id: string;
  company_id: string;
  comparison_report: Record<string, unknown>;
  baseline_skill_version_id: string;
  candidate_skill_version_id: string;
  [key: string]: unknown;
}

export function createEvolutionEvaluation(proposalId: string, payload: {
  company_id: string;
  baseline: Record<string, unknown>;
  candidate: Record<string, unknown>;
  policy: Record<string, unknown>;
  actor_id?: string;
}) {
  return apiClient.post<EvaluationReport>(`/control-plane/evolution-proposals/${proposalId}/evaluations`, payload);
}

export function listEvolutionEvaluations(proposalId: string, companyId: string) {
  return apiClient.get<{ evaluations: EvaluationReport[]; total: number; report_kind: "fixed_evaluation_case_comparison" }>(
    `/control-plane/evolution-proposals/${proposalId}/evaluations`, { company_id: companyId },
  );
}

export interface EvolutionReleasePayload {
  company_id: string;
  evaluation_report_id: string;
  skill_id: string;
  agent_id: string;
  baseline_version: number;
  candidate_version: number;
  baseline_config_hash: string;
  candidate_config_hash: string;
  action: "shadow" | "canary" | "promote" | "rollback";
}

export function requestEvolutionRelease(proposalId: string, payload: EvolutionReleasePayload) {
  return apiClient.post<Record<string, unknown>>(`/control-plane/evolution-proposals/${proposalId}/release`, payload);
}

export function reconcileEvolutionRelease(proposalId: string, companyId: string) {
  return apiClient.post<Record<string, unknown>>(
    `/control-plane/evolution-proposals/${proposalId}/release/reconcile?company_id=${encodeURIComponent(companyId)}`,
  );
}

export function recoverEvolutionRelease(proposalId: string, companyId: string) {
  return apiClient.post<Record<string, unknown>>(
    `/control-plane/evolution-proposals/${proposalId}/release/recover?company_id=${encodeURIComponent(companyId)}`,
  );
}
