"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import {
  agentDefinitionsToMetas,
  getAllAgents,
  useAgents,
  useControlPlaneAgents,
  type AgentMeta,
  type AgentRuntimeStatus,
  type AgentStatus,
  type ControlPlaneAgentDefinition,
} from "@/entities/agent";
import { AgentCreateDialog } from "@/features/agent-create";
import { PageHeader } from "@/shared/ui/page-header";
import { Skeleton } from "@/shared/ui/skeleton";
import {
  AgentFleetFilters,
  type AgentFleetFiltersState,
} from "./agent-fleet-filters";
import { AgentFleetOverview } from "./agent-fleet-overview";

function mapControlPlaneStatus(status: string): AgentStatus {
  const normalized = status.toLowerCase();
  if (normalized === "running") return "running";
  if (normalized === "error") return "error";
  if (normalized === "paused" || normalized === "terminated") return "stopped";
  return "idle";
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
    const status = definition ? mapControlPlaneStatus(definition.status) : "stopped";
    const health = status === "stopped" ? 0 : status === "error" ? 35 : 90;

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

      <AgentFleetFilters filters={filters} onFiltersChange={setFilters} />

      {isLoading || runtimeQuery.isLoading ? (
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
