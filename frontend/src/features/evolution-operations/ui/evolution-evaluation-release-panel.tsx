"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";

import {
  createEvolutionEvaluation,
  listEvolutionEvaluations,
  reconcileEvolutionRelease,
  recoverEvolutionRelease,
  requestEvolutionRelease,
  type EvaluationReport,
  type EvolutionReleasePayload,
} from "../api/evolution-operations";

type Proposal = { proposal_id: string; company_id: string; metadata: Record<string, unknown> };
type EvaluationInput = { baseline: Record<string, unknown>; candidate: Record<string, unknown>; policy: Record<string, unknown> };
const blankEvaluation = "";
const RELEASE_ACTIONS: EvolutionReleasePayload["action"][] = ["shadow", "canary", "promote", "rollback"];

function validateEvaluation(value: unknown): value is EvaluationInput {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  for (const name of ["baseline", "candidate"]) {
    const batch = data[name];
    if (!batch || typeof batch !== "object") return false;
    const row = batch as Record<string, unknown>;
    if (typeof row.evaluation_id !== "string" || typeof row.dataset_revision !== "string" ||
      typeof row.config_revision !== "string" || !/^.+@[1-9][0-9]*$/.test(row.config_revision) || typeof row.budget_usd !== "number" ||
      !Array.isArray(row.cases) || !Array.isArray(row.results)) return false;
    const caseIds = new Set<string>();
    for (const item of row.cases) {
      if (!item || typeof item !== "object") return false;
      const testCase = item as Record<string, unknown>;
      if (typeof testCase.case_id !== "string" || typeof testCase.case_revision !== "string" ||
        (testCase.expects_policy_denial !== undefined && typeof testCase.expects_policy_denial !== "boolean") || caseIds.has(testCase.case_id)) return false;
      caseIds.add(testCase.case_id);
    }
    const resultIds = new Set<string>();
    const resultCases = new Set<string>();
    for (const item of row.results) {
      if (!item || typeof item !== "object") return false;
      const result = item as Record<string, unknown>;
      if (typeof result.result_id !== "string" || typeof result.case_id !== "string" ||
        typeof result.config_revision !== "string" || typeof result.accepted !== "boolean" ||
        typeof result.quality !== "number" || typeof result.total_attempt_cost_usd !== "number" ||
        typeof result.latency_ms !== "number" || typeof result.human_interventions !== "number" ||
        (result.policy_denied !== undefined && typeof result.policy_denied !== "boolean") ||
        (result.policy_violation !== undefined && typeof result.policy_violation !== "boolean") ||
        resultIds.has(result.result_id) || resultCases.has(result.case_id) || !caseIds.has(result.case_id) ||
        result.config_revision !== row.config_revision) return false;
      resultIds.add(result.result_id);
      resultCases.add(result.case_id);
    }
  }
  const policy = data.policy;
  return Boolean(policy && typeof policy === "object" && typeof (policy as Record<string, unknown>).maximum_cost_per_accepted_outcome_usd === "number");
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

export function EvolutionEvaluationReleasePanel({ proposal }: { proposal: Proposal }) {
  const t = useTranslations("evolutionOperations");
  const [json, setJson] = useState(blankEvaluation);
  const [report, setReport] = useState<EvaluationReport>();
  const [reports, setReports] = useState<EvaluationReport[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reconcilePending, setReconcilePending] = useState(false);
  const metadata = proposal.metadata;
  const [release, setRelease] = useState({
    skill_id: typeof metadata.skill_id === "string" ? metadata.skill_id : "",
    agent_id: typeof metadata.agent_id === "string" ? metadata.agent_id : "",
    baseline_version: typeof metadata.baseline_version === "number" ? String(metadata.baseline_version) : "",
    candidate_version: typeof metadata.candidate_version === "number" ? String(metadata.candidate_version) : "",
    baseline_config_hash: typeof metadata.baseline_config_hash === "string" ? metadata.baseline_config_hash : "",
    candidate_config_hash: typeof metadata.candidate_config_hash === "string" ? metadata.candidate_config_hash : "",
  });

  useEffect(() => {
    let active = true;
    void listEvolutionEvaluations(proposal.proposal_id, proposal.company_id).then((result) => {
      if (active) setReports(result.evaluations);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => { active = false; };
  }, [proposal.company_id, proposal.proposal_id]);

  const selected = useMemo(() => report ?? reports[0], [report, reports]);
  const liveReady = Boolean(selected && Number(record(selected.comparison_report.baseline).sample_count) >= 50 &&
    Number(record(selected.comparison_report.candidate).sample_count) >= 50);

  async function evaluate() {
    setBusy(true); setError(""); setMessage("");
    try {
      const parsed: unknown = JSON.parse(json);
      if (!validateEvaluation(parsed)) throw new Error(t("invalidBatch"));
      const created = await createEvolutionEvaluation(proposal.proposal_id, {
        company_id: proposal.company_id, ...parsed, actor_id: "human:operator",
      });
      setReport(created);
      setReports((current) => [created, ...current]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function releaseAction(action: EvolutionReleasePayload["action"]) {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const payload: EvolutionReleasePayload = {
        company_id: proposal.company_id,
        evaluation_report_id: selected.evaluation_report_id,
        skill_id: release.skill_id.trim(), agent_id: release.agent_id.trim(),
        baseline_version: Number(release.baseline_version), candidate_version: Number(release.candidate_version),
        baseline_config_hash: release.baseline_config_hash.trim(), candidate_config_hash: release.candidate_config_hash.trim(),
        action,
      };
      if (!payload.skill_id || !payload.agent_id || !Number.isInteger(payload.baseline_version) ||
        payload.baseline_version < 1 || !Number.isInteger(payload.candidate_version) || payload.candidate_version < 1 ||
        !/^[a-f0-9]{64}$/.test(payload.baseline_config_hash) || !/^[a-f0-9]{64}$/.test(payload.candidate_config_hash)) {
        throw new Error(t("invalidRelease"));
      }
      if (selected.baseline_skill_version_id !== `${payload.skill_id}@${payload.baseline_version}` ||
        selected.candidate_skill_version_id !== `${payload.skill_id}@${payload.candidate_version}`) {
        throw new Error(t("configRevisionMismatch"));
      }
      if ((action === "canary" || action === "promote") && !liveReady) throw new Error(t("liveSampleGate"));
      const response = await requestEvolutionRelease(proposal.proposal_id, payload);
      setReconcilePending(false);
      setMessage(`${t("receiverAcknowledged")} ${JSON.stringify(response)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      if (cause instanceof Error && cause.message.includes("evolution_release_pending_reconciliation")) {
        setReconcilePending(true);
      }
    } finally { setBusy(false); }
  }

  async function reconcileRelease() {
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await reconcileEvolutionRelease(proposal.proposal_id, proposal.company_id);
      setReconcilePending(false);
      setMessage(`${t("reconcileCompleted")} ${JSON.stringify(response)}`);
    } catch (cause) {
      setReconcilePending(true);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function recoverRelease() {
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await recoverEvolutionRelease(proposal.proposal_id, proposal.company_id);
      setReconcilePending(false);
      setMessage(`${t("recoveryCompleted")} ${JSON.stringify(response)}`);
    } catch (cause) {
      setReconcilePending(true);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  return (
    <section className="mt-3 space-y-3 rounded-lg border p-3" aria-label={t("title")}>
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <p className="text-xs text-muted-foreground">{t("fixedCaseDisclaimer")}</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {message && <p role="status" className="break-all text-sm">{message}</p>}
      <label className="block space-y-1 text-xs font-medium">
        <span>{t("batchJson")}</span>
        <Textarea className="min-h-48 font-mono text-xs" value={json} onChange={(event) => setJson(event.target.value)} placeholder={t("batchPlaceholder")} />
      </label>
      <Button size="sm" disabled={busy || !json.trim()} onClick={() => void evaluate()}>{t("evaluate")}</Button>
      {selected && <div className="space-y-2 rounded-md bg-muted/40 p-3">
        <p className="text-xs font-medium">{t("reportKind")}: {String(selected.comparison_report.report_kind ?? "fixed_evaluation_case_comparison")}</p>
        <p className="text-xs text-muted-foreground">{t("liveSampleStatus")}: {liveReady ? t("liveSampleReady") : t("liveSampleInsufficient")}</p>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(selected.comparison_report, null, 2)}</pre>
      </div>}
      <div className="grid gap-2 sm:grid-cols-2">
        {(["skill_id", "agent_id", "baseline_version", "candidate_version", "baseline_config_hash", "candidate_config_hash"] as const).map((key) => (
          <Input key={key} aria-label={t(key)} placeholder={t(key)} value={release[key]} onChange={(event) => setRelease((current) => ({ ...current, [key]: event.target.value }))} />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {RELEASE_ACTIONS.map((action) => <Button key={action} size="sm" variant={action === "promote" ? "default" : "outline"}
          disabled={busy || !selected || !release.skill_id.trim() || !release.agent_id.trim() ||
            ((action === "canary" || action === "promote") && !liveReady)} onClick={() => void releaseAction(action)}>
          {t(action)}
        </Button>)}
      </div>
      <p className="text-xs text-muted-foreground">{t("releaseApprovalNote")}</p>
      <div className={`flex flex-wrap items-center gap-2 rounded-md border p-3 ${reconcilePending ? "border-amber-400/60 bg-amber-50/50 dark:bg-amber-950/20" : ""}`}>
        <div className="min-w-0 flex-1 space-y-1 text-xs text-muted-foreground">
          <p>{t(reconcilePending ? "releasePending" : "reconcileNote")}</p>
          <p>{t("recoveryNote")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void reconcileRelease()}>{t("reconcileRelease")}</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void recoverRelease()}>{t("recoverRelease")}</Button>
        </div>
      </div>
    </section>
  );
}
