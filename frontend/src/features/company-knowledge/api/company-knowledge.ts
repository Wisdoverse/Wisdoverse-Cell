import { apiClient } from "@/lib/api/client";

export interface CompanyKnowledgeRecord {
  knowledge_id: string;
  company_id: string;
  source_artifact_id: string;
  source_company_id: string;
  owner_actor_id: string;
  reader_role_ids: string[];
  version: number;
  retention_until: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  deleted_by_actor_id: string | null;
}

export function createCompanyKnowledge(payload: {
  company_id: string;
  source_artifact_id: string;
  reader_role_ids: string[];
  retention_until: string | null;
}) {
  return apiClient.post<CompanyKnowledgeRecord>("/control-plane/knowledge", payload);
}

export function readCompanyKnowledge(knowledgeId: string, companyId: string) {
  return apiClient.get<{ knowledge: CompanyKnowledgeRecord; source_artifact: { artifact_id: string; company_id: string; uri: string; content_hash: string | null } }>(
    `/control-plane/knowledge/${encodeURIComponent(knowledgeId)}`,
    { company_id: companyId },
  );
}

export function reviseCompanyKnowledge(knowledgeId: string, payload: {
  company_id: string;
  source_artifact_id: string;
  reader_role_ids: string[];
  retention_until: string | null;
  expected_version: number;
}) {
  return apiClient.post<CompanyKnowledgeRecord>(`/control-plane/knowledge/${encodeURIComponent(knowledgeId)}/publish`, payload);
}

export function deleteCompanyKnowledge(knowledgeId: string, companyId: string) {
  return apiClient.delete<Record<string, unknown>>(
    `/control-plane/knowledge/${encodeURIComponent(knowledgeId)}?company_id=${encodeURIComponent(companyId)}`,
  );
}
