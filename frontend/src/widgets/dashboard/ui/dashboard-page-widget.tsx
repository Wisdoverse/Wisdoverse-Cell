"use client";

import { useTranslations } from "next-intl";
import { AlertCircle } from "lucide-react";

import { FleetSummaryCard } from "@/components/dashboard/fleet-summary-card";
import { LLMUsageCard } from "@/components/dashboard/llm-usage-card";
import { QuickActions } from "@/components/dashboard/quick-actions";
import { StatsRow } from "@/components/dashboard/stats-row";
import { StatusChart } from "@/components/dashboard/status-chart";
import { TrendChart } from "@/components/dashboard/trend-chart";
import { PageHeader } from "@/shared/ui/page-header";
import {
  useCircuitBreaker,
  useEnhancedStats,
  useLLMUsage,
} from "@/entities/control-plane/model/use-operations-metrics";

export function DashboardPageWidget() {
  const t = useTranslations("dashboard");
  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useEnhancedStats();
  const { data: llm, isLoading: llmLoading, error: llmError } = useLLMUsage();
  const { data: cb } = useCircuitBreaker();

  const statusCounts = stats?.requirements_by_status || {};

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      {(statsError || llmError) && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{t("loadError")}</span>
        </div>
      )}
      <StatsRow counts={statusCounts} isLoading={statsLoading} />
      <FleetSummaryCard />
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <StatusChart counts={statusCounts} isLoading={statsLoading} />
        <LLMUsageCard data={llm} circuitBreaker={cb} isLoading={llmLoading} />
      </div>
      <TrendChart data={stats?.weekly_trend} isLoading={statsLoading} />
      <QuickActions />
    </div>
  );
}
