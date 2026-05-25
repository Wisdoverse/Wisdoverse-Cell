"use client";

import { useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Timer } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import useSWR from "swr";

import {
  ActivityFiltersBar,
  type ActivityFilters,
} from "./activity-filters";
import { ActivityTimeline } from "./activity-timeline";
import { PageHeader } from "@/shared/ui/page-header";
import { controlPlaneRunsToActivityEvents } from "@/entities/activity";
import {
  listControlPlaneRuns,
  type AgentRunStatus,
  type ControlPlaneAgentRun,
} from "@/entities/control-plane";
import { AGENT_REGISTRY } from "@/entities/agent";
import { cn } from "@/lib/utils";

type ActivitySummaryKey = "total" | "running" | "attention" | "completed";

interface ActivitySummaryMetric {
  key: ActivitySummaryKey;
  value: number;
  icon: LucideIcon;
  tone: "slate" | "sky" | "amber" | "emerald";
}

const attentionStatuses = new Set<AgentRunStatus>([
  "failed",
  "cancelled",
  "timed_out",
]);

function summaryToneClass(tone: ActivitySummaryMetric["tone"]): string {
  return {
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-900/50 dark:text-slate-200",
    sky: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-200",
    amber:
      "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-200",
    emerald:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200",
  }[tone];
}

function summarizeRuns(runs: ControlPlaneAgentRun[]): ActivitySummaryMetric[] {
  let running = 0;
  let attention = 0;
  let completed = 0;

  for (const run of runs) {
    if (run.status === "running" || run.status === "pending") running += 1;
    if (attentionStatuses.has(run.status)) attention += 1;
    if (run.status === "succeeded") completed += 1;
  }

  return [
    { key: "total", value: runs.length, icon: Activity, tone: "slate" },
    { key: "running", value: running, icon: Timer, tone: "sky" },
    { key: "attention", value: attention, icon: AlertTriangle, tone: "amber" },
    { key: "completed", value: completed, icon: CheckCircle2, tone: "emerald" },
  ];
}

function ActivitySummary({ metrics }: { metrics: ActivitySummaryMetric[] }) {
  const t = useTranslations("activity");

  return (
    <section
      aria-label={t("summaryAriaLabel")}
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      {metrics.map((metric) => {
        const Icon = metric.icon;
        return (
          <div key={metric.key} className="rounded-lg border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-3xl font-semibold leading-none tracking-normal tabular-nums">
                  {metric.value}
                </div>
                <p className="mt-2 text-sm font-medium">
                  {t(`summary.${metric.key}.label`)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t(`summary.${metric.key}.description`)}
                </p>
              </div>
              <div
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-lg",
                  summaryToneClass(metric.tone),
                )}
              >
                <Icon className="size-5" />
              </div>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export function ActivityPageWidget() {
  const t = useTranslations("activity");
  const [filters, setFilters] = useState<ActivityFilters>({});
  const { data, error, isLoading } = useSWR(["activity-control-plane-runs"], () =>
    listControlPlaneRuns({ limit: 100 }),
  );

  const runs = useMemo(() => data?.runs ?? [], [data?.runs]);
  const events = useMemo(
    () =>
      controlPlaneRunsToActivityEvents(runs, (run) =>
        t("runEvent", {
          runId: run.run_id,
          status: t(`runStatuses.${run.status}`),
        }),
      ),
    [runs, t],
  );
  const filteredEvents = useMemo(
    () =>
      filters.domain
        ? events.filter((event) => {
            const agentMeta = AGENT_REGISTRY[event.agent_id];
            return agentMeta?.domain === filters.domain;
          })
        : events,
    [events, filters.domain],
  );
  const summary = useMemo(() => summarizeRuns(runs), [runs]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <ActivityFiltersBar filters={filters} onFiltersChange={setFilters} />
        }
      />
      {!isLoading && !error ? <ActivitySummary metrics={summary} /> : null}
      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t("loading")}</p>
      ) : error ? (
        <p className="text-sm text-destructive">{t("loadError")}</p>
      ) : (
        <ActivityTimeline events={filteredEvents} />
      )}
    </div>
  );
}
