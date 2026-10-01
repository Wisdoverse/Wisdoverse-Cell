"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { ControlPlaneAgentRun } from "@/entities/control-plane";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";

import { recoverAbandonedExecution, requestExecutionControl, type ExecutionControlAction } from "../api/execution-controls";

// The backend control contract currently supports only the supervised process adapter.
const PROCESS_ADAPTER = "process";

export function ExecutionControlsPanel({ run, onRefresh }: { run: ControlPlaneAgentRun; onRefresh: () => void }) {
  const t = useTranslations("executionControls");
  const [reason, setReason] = useState("");
  const [recoveryReason, setRecoveryReason] = useState("");
  const [effectsReviewed, setEffectsReviewed] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const adapterType = run.metadata.adapter_type;
  if (run.status !== "running" || adapterType !== PROCESS_ADAPTER) return null;

  async function sendControl(action: ExecutionControlAction) {
    setPending(true);
    setError("");
    try {
      const response = await requestExecutionControl(run.run_id, {
        company_id: run.company_id,
        action,
        reason: reason.trim(),
      });
      setMessage(t("controlRequested", { action: response.requested_action, state: response.state }));
      setReason("");
      onRefresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setPending(false);
    }
  }

  async function recover() {
    setPending(true);
    setError("");
    try {
      const response = await recoverAbandonedExecution(run.run_id, {
        company_id: run.company_id,
        reason: recoveryReason.trim(),
        effects_reconciled: true,
      });
      setMessage(t("recoveryCompleted", { state: response.state, handoff: response.handoff }));
      setRecoveryReason("");
      setEffectsReviewed(false);
      onRefresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mt-3 space-y-3 rounded-lg border border-amber-300/70 bg-amber-50/50 p-3 dark:border-amber-900/50 dark:bg-amber-950/20" aria-label={t("title")}>
      <div>
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <p className="text-xs text-muted-foreground">{t("runningStatus", { status: run.status, adapter: adapterType })}</p>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {message && <p role="status" className="text-sm">{message} {t("requestMayNotBeApplied")}</p>}
      <div className="space-y-2">
        <Input aria-label={t("controlReason")} value={reason} onChange={(event) => setReason(event.target.value)} placeholder={t("controlReasonPlaceholder")} />
        <div className="flex flex-wrap gap-2">
          {(["pause", "resume", "terminate"] as const).map((action) => (
            <Button key={action} size="sm" variant={action === "terminate" ? "destructive" : "outline"} disabled={pending || !reason.trim()} onClick={() => void sendControl(action)}>
              {t(action)}
            </Button>
          ))}
        </div>
      </div>
      <div className="space-y-2 border-t pt-3">
        <p className="text-xs text-muted-foreground">{t("recoveryDescription")}</p>
        <Input aria-label={t("recoveryReason")} value={recoveryReason} onChange={(event) => setRecoveryReason(event.target.value)} placeholder={t("recoveryReasonPlaceholder")} />
        <label className="flex items-start gap-2 text-xs leading-5">
          <input type="checkbox" checked={effectsReviewed} onChange={(event) => setEffectsReviewed(event.target.checked)} />
          <span>{t("effectsReviewed")}</span>
        </label>
        <Button size="sm" variant="outline" disabled={pending || !recoveryReason.trim() || !effectsReviewed} onClick={() => void recover()}>{t("recover")}</Button>
      </div>
    </section>
  );
}
