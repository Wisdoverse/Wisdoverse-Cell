"use client";

import { useMemo, useState } from "react";
import { Activity, AlertTriangle, Bot, PauseCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import {
  agentDefinitionsToMetas,
  getAllAgents,
  mapControlPlaneLifecycleStatus,
  useAgents,
  useControlPlaneAgents,
  type AgentMeta,
  type AgentRuntimeStatus,
  type ControlPlaneAgentDefinition,
} from "@/entities/agent";
import { AgentCreateDialog } from "@/features/agent-create";
import { PageHeader } from "@/shared/ui/page-header";
import { Skeleton } from "@/shared/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  AgentFleetFilters,
  type AgentFleetFiltersState,
} from "./agent-fleet-filters";
import { AgentFleetOverview } from "./agent-fleet-overview";

type FleetSummaryKey = "total" | "running" | "attention" | "offline";

interface FleetSummaryMetric {
  key: FleetSummaryKey;
  value: number;
  icon: LucideIcon;
  tone: "slate" | "emerald" | "amber" | "rose";
}

function buildRuntimes(
  agents: AgentMeta[],
  definitions: ControlPlaneAgentDefinition[],
  runtimeRows: AgentRuntimeStatus[],
): Record<string, AgentRuntimeStatus> {
  const definitionById = new Map(
    definitions.map((definition) => [definition.agent_id, definition]),
  );
  const runtimeById = new Map(runtimeRows.map((runtime) => [runtime.agent_id, runtime]));

  return agents.reduce<Record<string, AgentRuntimeStatus>>((acc, agent) => {
    const runtime = runtimeById.get(agent.id);
    if (runtime) {
      acc[agent.id] = runtime;
      return acc;
    }

    const definition = definitionById.get(agent.id);
    const status = definition ? mapControlPlaneLifecycleStatus(definition.status) : "stopped";
    const isOffline = status === "paused" || status === "stopped";
    const health = isOffline ? 0 : status === "error" ? 35 : 60;

    acc[agent.id] = {
      agent_id: agent.id,
      status,
      health,
      task_count: 0,
      pending_count: 0,
      error_count: status === "error" ? 1 : 0,
      uptime_seconds: 0,
      last_active_at: definition?.updated_at ?? new Date(0).toISOString(),
    };
    return acc;
  }, {});
}

function mergeAgents(
  builtinAgents: AgentMeta[],
  controlPlaneAgents: AgentMeta[],
): AgentMeta[] {
  const byId = new Map<string, AgentMeta>();
  for (const agent of builtinAgents) byId.set(agent.id, agent);
  for (const agent of controlPlaneAgents) byId.set(agent.id, agent);
  return [...byId.values()];
}

function summaryToneClass(tone: FleetSummaryMetric["tone"]): string {
  return {
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-900/50 dark:text-slate-200",
    emerald:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200",
    amber:
      "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-200",
    rose: "bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-200",
  }[tone];
}

function AgentFleetSummary({ metrics }: { metrics: FleetSummaryMetric[] }) {
  const t = useTranslations("agents");

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

export function AgentFleetPage() {
  const t = useTranslations("agents");
  const [filters, setFilters] = useState<AgentFleetFiltersState>({
    status: "all",
    agentKind: "all",
    search: "",
  });
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useControlPlaneAgents({ limit: 500 });
  const runtimeQuery = useAgents();

  const controlPlaneDefinitions = useMemo(() => data?.agents ?? [], [data?.agents]);
  const agents = useMemo(
    () =>
      mergeAgents(
        getAllAgents(),
        agentDefinitionsToMetas(controlPlaneDefinitions),
      ),
    [controlPlaneDefinitions],
  );
  const runtimes = useMemo(
    () => buildRuntimes(agents, controlPlaneDefinitions, runtimeQuery.data?.agents ?? []),
    [agents, controlPlaneDefinitions, runtimeQuery.data?.agents],
  );
  const isFleetLoading = isLoading || runtimeQuery.isLoading;
  const fleetSummaryMetrics = useMemo<FleetSummaryMetric[]>(() => {
    let running = 0;
    let attention = 0;
    let offline = 0;

    for (const agent of agents) {
      const runtime = runtimes[agent.id];
      if (!runtime) continue;
      if (runtime.status === "running") running += 1;
      if (
        runtime.status === "warning" ||
        runtime.status === "error" ||
        runtime.error_count > 0
      ) {
        attention += 1;
      }
      if (runtime.status === "paused" || runtime.status === "stopped") {
        offline += 1;
      }
    }

    return [
      { key: "total", value: agents.length, icon: Bot, tone: "slate" },
      { key: "running", value: running, icon: Activity, tone: "emerald" },
      { key: "attention", value: attention, icon: AlertTriangle, tone: "amber" },
      { key: "offline", value: offline, icon: PauseCircle, tone: "rose" },
    ];
  }, [agents, runtimes]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <AgentCreateDialog
            availableAgents={agents}
            onCreated={() => mutate()}
          />
        }
      />

      {isFleetLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28 rounded-lg" />
          ))}
        </div>
      ) : (
        <AgentFleetSummary metrics={fleetSummaryMetrics} />
      )}

      <AgentFleetFilters filters={filters} onFiltersChange={setFilters} />

      {isFleetLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-44 rounded-lg" />
          ))}
        </div>
      ) : (
        <>
          {error && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              {t("controlPlaneLoadError")}
            </div>
          )}
          {runtimeQuery.error && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              {t("runtimeLoadError")}
            </div>
          )}
          <AgentFleetOverview
            agents={agents}
            runtimes={runtimes}
            filters={filters}
          />
        </>
      )}
    </div>
  );
}
