"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";

import {
  createCompanyKnowledge,
  deleteCompanyKnowledge,
  readCompanyKnowledge,
  reviseCompanyKnowledge,
  type CompanyKnowledgeRecord,
} from "../api/company-knowledge";

function parseRoleIds(value: string): string[] {
  return [...new Set(value.split(",").map((role) => role.trim()).filter(Boolean))];
}

function retentionValue(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error("invalid_retention_date");
  return date.toISOString();
}

export function CompanyKnowledgePanel({ companyId }: { companyId: string }) {
  const t = useTranslations("companyKnowledge");
  const [artifactId, setArtifactId] = useState("");
  const [roleIds, setRoleIds] = useState("");
  const [retention, setRetention] = useState("");
  const [lookupId, setLookupId] = useState("");
  const [record, setRecord] = useState<CompanyKnowledgeRecord>();
  const [sourceArtifact, setSourceArtifact] = useState<{ artifact_id: string; uri: string; content_hash: string | null }>();
  const [deleteReviewed, setDeleteReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function act(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  function payload() {
    return {
      company_id: companyId,
      source_artifact_id: artifactId.trim(),
      reader_role_ids: parseRoleIds(roleIds),
      retention_until: retentionValue(retention),
    };
  }

  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div>
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        <Input aria-label={t("sourceArtifact")} value={artifactId} onChange={(event) => setArtifactId(event.target.value)} placeholder={t("sourceArtifactPlaceholder")} />
        <Input aria-label={t("readerRoles")} value={roleIds} onChange={(event) => setRoleIds(event.target.value)} placeholder={t("readerRolesPlaceholder")} />
        <div className="space-y-1">
          <label className="text-sm" htmlFor="knowledge-retention">{t("retention")}</label>
          <Input id="knowledge-retention" type="datetime-local" value={retention} onChange={(event) => setRetention(event.target.value)} />
        </div>
        <div className="flex items-end gap-2">
          <Button disabled={busy || !companyId.trim() || !artifactId.trim()} onClick={() => void act(async () => {
            const created = await createCompanyKnowledge(payload());
            setRecord(created); setLookupId(created.knowledge_id);
          })}>{t("create")}</Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 border-t pt-4">
        <Input aria-label={t("knowledgeId")} value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder={t("knowledgeIdPlaceholder")} />
        <Button variant="outline" disabled={busy || !lookupId.trim() || !companyId.trim()} onClick={() => void act(async () => {
          const result = await readCompanyKnowledge(lookupId.trim(), companyId.trim());
          setRecord(result.knowledge); setSourceArtifact(result.source_artifact); setArtifactId(result.knowledge.source_artifact_id);
          setRoleIds(result.knowledge.reader_role_ids.join(", "));
          setRetention(result.knowledge.retention_until ? new Date(result.knowledge.retention_until).toISOString().slice(0, 16) : "");
          setDeleteReviewed(false);
        })}>{t("read")}</Button>
      </div>
      {record && <div className="space-y-3 rounded-lg border p-4" aria-label={t("record")}>
        <dl className="grid gap-2 text-sm md:grid-cols-2">
          <div><dt className="text-muted-foreground">{t("knowledgeId")}</dt><dd className="font-mono">{record.knowledge_id}</dd></div>
          <div><dt className="text-muted-foreground">{t("version")}</dt><dd>{record.version}</dd></div>
          <div><dt className="text-muted-foreground">{t("owner")}</dt><dd>{record.owner_actor_id}</dd></div>
          <div><dt className="text-muted-foreground">{t("readerRoles")}</dt><dd>{record.reader_role_ids.join(", ") || t("noRoleReaders")}</dd></div>
          <div><dt className="text-muted-foreground">{t("sourceArtifact")}</dt><dd>{record.source_artifact_id}</dd></div>
          <div><dt className="text-muted-foreground">{t("retention")}</dt><dd>{record.retention_until ?? t("noRetentionExpiry")}</dd></div>
        </dl>
        {sourceArtifact && <a className="text-sm underline" href={sourceArtifact.uri} target="_blank" rel="noreferrer">{t("openSourceArtifact")}</a>}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" disabled={busy || !artifactId.trim()} onClick={() => void act(async () => {
            const revised = await reviseCompanyKnowledge(record.knowledge_id, { ...payload(), expected_version: record.version });
            setRecord(revised);
          })}>{t("reviseAccess")}</Button>
          <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={deleteReviewed} onChange={(event) => setDeleteReviewed(event.target.checked)} /><span>{t("deleteReview")}</span></label>
          <Button variant="destructive" disabled={busy || !deleteReviewed} onClick={() => void act(async () => {
            await deleteCompanyKnowledge(record.knowledge_id, companyId);
            setRecord(undefined); setSourceArtifact(undefined); setDeleteReviewed(false);
          })}>{t("delete")}</Button>
        </div>
      </div>}
    </section>
  );
}
