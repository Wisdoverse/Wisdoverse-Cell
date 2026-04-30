"use client";

import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/shared/page-header";
import { HealthGrid } from "@/components/monitor/health-grid";
import { LLMStatsPanel } from "@/components/monitor/llm-stats-panel";
import { CircuitBreakerCard } from "@/components/monitor/circuit-breaker-card";
import { AlertCircle } from "lucide-react";
import {
  useHealthReady,
  useLLMUsage,
  useCircuitBreaker,
} from "@/lib/hooks/use-llm-usage";

export default function MonitorPage() {
  const t = useTranslations("monitor");
  const { data: health, isLoading: healthLoading, error: healthError } = useHealthReady();
  const { data: llm, isLoading: llmLoading, error: llmError } = useLLMUsage();
  const { data: cb, isLoading: cbLoading, error: cbError } = useCircuitBreaker();

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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <LLMStatsPanel data={llm} isLoading={llmLoading} />
        </div>
        <CircuitBreakerCard data={cb} isLoading={cbLoading} />
      </div>
    </div>
  );
}
