import { apiClient } from "@/lib/api/client";

export interface PortableCompanyTemplate {
  schema_version: "1.0";
  company: { name: string; mission: string };
  goals: Array<Record<string, unknown>>;
  roles: Array<Record<string, unknown>>;
  playbooks: Array<Record<string, unknown>>;
}

export interface CompanyTemplateImportResult {
  company_id: string;
  goal_ids: Record<string, string>;
  role_ids: Record<string, string>;
}

export function exportCompanyTemplate(companyId: string) {
  return apiClient.get<PortableCompanyTemplate>(`/control-plane/companies/${encodeURIComponent(companyId)}/template`);
}

export function importCompanyTemplate(template: PortableCompanyTemplate, permissionsReviewed: boolean) {
  return apiClient.post<CompanyTemplateImportResult>("/control-plane/company-templates/import", {
    template,
    permissions_reviewed: permissionsReviewed,
  });
}
