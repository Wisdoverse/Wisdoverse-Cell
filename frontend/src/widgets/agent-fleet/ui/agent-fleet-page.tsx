"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import {
  agentDefinitionsToMetas,
  getAllAgents,
  mapControlPlaneAgentStatus,
  useControlPlaneAgents,
  type AgentMeta,
  type AgentRuntimeStatus,
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

function seedRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function buildRuntimes(
  agents: AgentMeta[],
  definitions: ControlPlaneAgentDefinition[],
): Record<string, AgentRuntimeStatus> {
  const definitionById = new Map(
    definitions.map((definition) => [definition.agent_id, definition]),
  );

  return agents.reduce<Record<string, AgentRuntimeStatus>>((acc, agent, index) => {
    const definition = definitionById.get(agent.id);
    const status = definition
      ? mapControlPlaneAgentStatus(definition.status)
      : "running";
    const isOffline = status === "paused" || status === "stopped";
    const health = isOffline ? 0 : status === "error" ? 35 : 90;

    acc[agent.id] = {
      agent_id: agent.id,
      status,
      health: definition ? health : 85 + Math.floor(seedRandom(index + 1) * 15),
      task_count: definition ? 0 : Math.floor(seedRandom(index + 10) * 200),
      pending_count: definition ? 0 : Math.floor(seedRandom(index + 20) * 10),
      error_count: status === "error" ? 1 : 0,
      uptime_seconds: definition ? 0 : 259200,
      last_active_at: definition?.updated_at ?? new Date().toISOString(),
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
    () => buildRuntimes(agents, controlPlaneDefinitions),
    [agents, controlPlaneDefinitions],
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

      {isLoading ? (
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
