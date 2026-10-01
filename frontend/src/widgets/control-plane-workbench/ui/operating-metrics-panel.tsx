"use client";

import { useLocale, useTranslations } from "next-intl";
import { useControlPlaneOperatingMetrics } from "@/entities/control-plane";
import { Skeleton } from "@/shared/ui/skeleton";

function formatNumber(value: number | null | undefined, locale: string, unknown: string, fractionDigits = 1): string {
  if (value == null || !Number.isFinite(value)) return unknown;
  return new Intl.NumberFormat(locale, { maximumFractionDigits: fractionDigits }).format(value);
}

function formatAge(value: number | null, locale: string, unknown: string, secondsUnit: string): string {
  if (value == null || !Number.isFinite(value)) return unknown;
  return `${formatNumber(value, locale, unknown)} ${secondsUnit}`;
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="min-w-0 rounded-lg border bg-background/70 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-lg font-semibold tabular-nums">{value}</p>
      {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function OperatingMetricsPanel({ companyId }: { companyId?: string }) {
  const t = useTranslations("operatingMetrics");
  const locale = useLocale();
  const query = useControlPlaneOperatingMetrics(companyId);
  const unknown = t("unknown");
  const secondsUnit = t("secondsUnit");

  return (
    <section className="rounded-lg border border-white/70 bg-white/80 p-4 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/50 dark:shadow-none" aria-label={t("title")}>
      <div className="mb-3">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("description")}</p>
      </div>
      {query.error && <p role="alert" className="mb-3 text-sm text-destructive">{t("unavailable", { error: query.error instanceof Error ? query.error.message : String(query.error) })}</p>}
      {query.isLoading && !query.data ? <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-24 rounded-lg" />)}</div> : query.data ? (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          <Metric
            label={t("queueP95")}
            value={formatAge(query.data.queue_delay.p95_seconds, locale, unknown, secondsUnit)}
            detail={t("queueSample", { size: query.data.queue_delay.sample_size, sampled: query.data.queue_delay.sampled_work_items, cap: query.data.queue_delay.sample_limit, excluded: query.data.queue_delay.excluded_without_run })}
          />
          <Metric
            label={t("pendingApprovals")}
            value={formatNumber(query.data.approvals.pending, locale, unknown, 0)}
            detail={t("oldestPendingAge", { age: formatAge(query.data.approvals.oldest_pending_age_seconds, locale, unknown, secondsUnit) })}
          />
          <Metric
            label={t("runSuccess")}
            value={query.data.runs.success_rate == null ? unknown : `${formatNumber(query.data.runs.success_rate * 100, locale, unknown)}%`}
            detail={t("runCount", { count: formatNumber(query.data.runs.total, locale, unknown, 0), errors: formatNumber(query.data.runs.adapter_errors, locale, unknown, 0) })}
          />
          <Metric
            label={t("acceptedOutcomes")}
            value={formatNumber(query.data.costs.accepted_outcome_count, locale, unknown, 0)}
            detail={t("allAttemptCost", { cost: formatNumber(query.data.costs.full_cost_usd_total, locale, unknown, 2) })}
          />
          <Metric
            label={t("unmeteredCoverage")}
            value={t("unmeteredOfRuns", { unmetered: formatNumber(query.data.costs.unmetered_run_count, locale, unknown, 0), total: formatNumber(query.data.runs.total, locale, unknown, 0) })}
            detail={t("meteredSources", { usage: formatNumber(query.data.costs.budget_usage_run_coverage, locale, unknown, 0), reported: formatNumber(query.data.costs.run_cost_coverage, locale, unknown, 0) })}
          />
          <Metric
            label={t("unresolvedLeases")}
            value={formatNumber(query.data.unresolved_execution_leases.count, locale, unknown, 0)}
            detail={t("oldestLeaseAge", { age: formatAge(query.data.unresolved_execution_leases.oldest_age_seconds, locale, unknown, secondsUnit) })}
          />
          <Metric
            label={t("pendingOutbox")}
            value={formatNumber(query.data.pending_outbox.count, locale, unknown, 0)}
            detail={t("oldestOutboxAge", { age: formatAge(query.data.pending_outbox.oldest_age_seconds, locale, unknown, secondsUnit) })}
          />
        </div>
      ) : !query.error ? <p className="text-sm text-muted-foreground">{t("unknown")}</p> : null}
    </section>
  );
}
