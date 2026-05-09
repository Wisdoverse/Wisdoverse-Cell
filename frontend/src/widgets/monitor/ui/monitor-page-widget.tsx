"use client";

import { useTranslations } from "next-intl";
import { AlertCircle } from "lucide-react";

import { CircuitBreakerCard } from "./circuit-breaker-card";
import { HealthGrid } from "./health-grid";
import { LLMStatsPanel } from "./llm-stats-panel";
import { PageHeader } from "@/shared/ui/page-header";
import {
  useCircuitBreaker,
  useHealthReady,
  useLLMUsage,
} from "@/entities/control-plane";

export function MonitorPageWidget() {
  const t = useTranslations("monitor");
  const {
    data: health,
    isLoading: healthLoading,
    error: healthError,
  } = useHealthReady();
  const { data: llm, isLoading: llmLoading, error: llmError } = useLLMUsage();
  const {
    data: cb,
    isLoading: cbLoading,
    error: cbError,
  } = useCircuitBreaker();

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      {(healthError || llmError || cbError) && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{t("loadError")}</span>
        </div>
      )}
      <HealthGrid data={health} isLoading={healthLoading} />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="md:col-span-2">
          <LLMStatsPanel data={llm} isLoading={llmLoading} />
        </div>
        <CircuitBreakerCard data={cb} isLoading={cbLoading} />
      </div>
    </div>
  );
}
