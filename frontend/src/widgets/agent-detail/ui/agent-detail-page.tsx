"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";

import {
  AGENT_REGISTRY,
  agentDefinitionsToMetas,
  agentDefinitionToMeta,
  getAllAgents,
  mapControlPlaneAgentStatus,
  useAgentDetail,
  useControlPlaneAgent,
  useControlPlaneAgents,
  type AgentRuntimeStatus,
} from "@/entities/agent";
import {
  useControlPlaneRuns,
  useControlPlaneWorkItems,
  type ControlPlaneAgentRun,
  type ControlPlaneWorkItem,
  type WorkItemStatus,
} from "@/entities/control-plane";
import { AgentEditDialog } from "@/features/agent-edit";
import { AgentControlActions } from "@/features/agent-wakeup";
import { AgentConfig } from "./agent-config";
import { AgentDetailLayout } from "./agent-detail-layout";
import { AgentEvents } from "./agent-events";
import { AgentOverview } from "./agent-overview";

interface AgentDetailPageProps {
  agentId: string;
}

const OPEN_WORK_STATUSES: WorkItemStatus[] = [
  "queued",
  "ready",
  "running",
  "blocked",
  "awaiting_approval",
];

function isFailedRun(run: ControlPlaneAgentRun): boolean {
  return run.status === "failed" || run.status === "timed_out";
}

function latestTimestamp(
  runtime: AgentRuntimeStatus,
  runs: ControlPlaneAgentRun[],
  workItems: ControlPlaneWorkItem[],
): string {
  const values: string[] = [
    runtime.last_active_at,
    ...runs.flatMap((run) =>
      run.completed_at ? [run.started_at, run.completed_at] : [run.started_at],
    ),
    ...workItems.map((workItem) => workItem.updated_at),
  ];
  return values.reduce((latest, value) =>
    new Date(value).getTime() > new Date(latest).getTime() ? value : latest,
  );
}

function runtimeWithControlPlaneCounts(input: {
  runtime: AgentRuntimeStatus;
  runs?: ControlPlaneAgentRun[];
  workItems?: ControlPlaneWorkItem[];
}): AgentRuntimeStatus {
  const runs = input.runs;
  const workItems = input.workItems;
  const failedRuns = runs?.filter(isFailedRun).length ?? 0;
  const failedWorkItems =
    workItems?.filter((workItem) => workItem.status === "failed").length ?? 0;

  return {
    ...input.runtime,
    task_count: runs ? runs.length : input.runtime.task_count,
    pending_count: workItems
      ? workItems.filter((workItem) => OPEN_WORK_STATUSES.includes(workItem.status))
          .length
      : input.runtime.pending_count,
    error_count: runs || workItems
      ? failedRuns + failedWorkItems
      : input.runtime.error_count,
    last_active_at:
      runs || workItems
        ? latestTimestamp(input.runtime, runs ?? [], workItems ?? [])
        : input.runtime.last_active_at,
  };
}

export function AgentDetailPage({ agentId }: AgentDetailPageProps) {
  const t = useTranslations("agentDetail");
  const tc = useTranslations("common");
  const builtinAgent = AGENT_REGISTRY[agentId];
  const runtimeQuery = useAgentDetail(agentId);
  const runsQuery = useControlPlaneRuns({ agent_id: agentId, limit: 100 });
  const workItemsQuery = useControlPlaneWorkItems({
    owner_agent_id: agentId,
    limit: 100,
  });
  const { data, error, isLoading, mutate } = useControlPlaneAgent(agentId);
  const controlPlaneAgents = useControlPlaneAgents({ limit: 500 });

  const agentMeta = useMemo(
    () => (data ? agentDefinitionToMeta(data) : builtinAgent),
    [builtinAgent, data],
  );
  const availableAgents = useMemo(() => {
    const byId = new Map(getAllAgents().map((agent) => [agent.id, agent]));
    for (const agent of agentDefinitionsToMetas(
      controlPlaneAgents.data?.agents ?? [],
    )) {
      byId.set(agent.id, agent);
    }
    return [...byId.values()];
  }, [controlPlaneAgents.data?.agents]);

  if (!agentMeta && isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <p>{tc("loading")}</p>
      </div>
    );
  }

  if (!agentMeta || (!builtinAgent && error)) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <p>{t("notFound")}</p>
      </div>
    );
  }

  const controlPlaneStatus = data ? mapControlPlaneAgentStatus(data.status) : "stopped";
  const baseRuntime =
    runtimeQuery.data ?? {
      agent_id: agentId,
      status: controlPlaneStatus,
      health:
        controlPlaneStatus === "running" || controlPlaneStatus === "idle"
          ? 90
          : 0,
      task_count: 0,
      pending_count: 0,
      error_count: controlPlaneStatus === "error" ? 1 : 0,
      uptime_seconds: 0,
      last_active_at: data?.updated_at ?? new Date(0).toISOString(),
    };
  const runtime = runtimeWithControlPlaneCounts({
    runtime: baseRuntime,
    runs: runsQuery.data?.runs,
    workItems: workItemsQuery.data?.work_items,
  });

  return (
    <div className="space-y-6">
      <AgentDetailLayout
        agentMeta={agentMeta}
        runtime={runtime}
        actions={
          data ? (
            <div className="flex flex-wrap justify-end gap-2">
              <AgentEditDialog
                agent={data}
                availableAgents={availableAgents}
                onUpdated={async (updated) => {
                  await mutate(updated, { revalidate: false });
                  await controlPlaneAgents.mutate();
                }}
              />
              <AgentControlActions
                agentId={agentId}
                status={data.status}
                onChanged={() =>
                  Promise.all([
                    mutate(),
                    runsQuery.mutate(),
                    workItemsQuery.mutate(),
                  ]).then(() => undefined)
                }
              />
            </div>
          ) : undefined
        }
      />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t("overview")}</TabsTrigger>
          <TabsTrigger value="events">{t("events")}</TabsTrigger>
          <TabsTrigger value="config">{t("config")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <AgentOverview agentMeta={agentMeta} runtime={runtime} />
        </TabsContent>

        <TabsContent value="events">
          <AgentEvents agentId={agentId} />
        </TabsContent>

        <TabsContent value="config">
          <AgentConfig agentMeta={agentMeta} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
