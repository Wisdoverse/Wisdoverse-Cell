"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";

import { exportCompanyTemplate, importCompanyTemplate, type CompanyTemplateImportResult, type PortableCompanyTemplate } from "../api/company-templates";

function downloadJson(name: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${name.replace(/[^a-z0-9-_]+/gi, "-") || "company-template"}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function isTemplate(value: unknown): value is PortableCompanyTemplate {
  if (!value || typeof value !== "object") return false;
  const template = value as Record<string, unknown>;
  return template.schema_version === "1.0" && typeof template.company === "object" &&
    Array.isArray(template.goals) && Array.isArray(template.roles) && Array.isArray(template.playbooks);
}

export function CompanyTemplatePanel({ companyId }: { companyId: string }) {
  const t = useTranslations("companyTemplate");
  const [json, setJson] = useState("");
  const [permissionsReviewed, setPermissionsReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CompanyTemplateImportResult>();

  async function exportTemplate() {
    setBusy(true); setError("");
    try {
      const template = await exportCompanyTemplate(companyId);
      downloadJson(template.company.name, template);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function importTemplate() {
    setBusy(true); setError(""); setResult(undefined);
    try {
      const parsed: unknown = JSON.parse(json);
      if (!isTemplate(parsed)) throw new Error(t("invalidTemplate"));
      const imported = await importCompanyTemplate(parsed, permissionsReviewed);
      setResult(imported);
      setJson("");
      setPermissionsReviewed(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div>
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="space-y-2">
        <Button type="button" variant="outline" disabled={busy || !companyId.trim()} onClick={() => void exportTemplate()}>{t("export")}</Button>
        <p className="text-xs text-muted-foreground">{t("exportPrivacy")}</p>
      </div>
      <div className="space-y-3 border-t pt-4">
        <label className="text-sm font-medium" htmlFor="company-template-json">{t("importJson")}</label>
        <Textarea id="company-template-json" className="min-h-56 font-mono text-xs" value={json} onChange={(event) => setJson(event.target.value)} placeholder={t("jsonPlaceholder")} />
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={permissionsReviewed} onChange={(event) => setPermissionsReviewed(event.target.checked)} />
          <span>{t("permissionsReview")}</span>
        </label>
        <p className="text-xs text-muted-foreground">{t("pausedRolesWarning")}</p>
        <Button type="button" disabled={busy || !permissionsReviewed || !json.trim()} onClick={() => void importTemplate()}>{t("import")}</Button>
      </div>
      {result && <div role="status" className="space-y-1 rounded-lg border p-3 text-sm">
        <p>{t("imported", { companyId: result.company_id })}</p>
        <p>{t("pausedRolesWarning")}</p>
      </div>}
    </section>
  );
}
