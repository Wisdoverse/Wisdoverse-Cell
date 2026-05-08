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
  useControlPlaneAgents,
  useControlPlaneAgent,
  type AgentRuntimeStatus,
} from "@/entities/agent";
import { AgentEditDialog } from "@/features/agent-edit";
import { AgentWakeupButton } from "@/features/agent-wakeup";
import { AgentConfig } from "./agent-config";
import { AgentDetailLayout } from "./agent-detail-layout";
import { AgentEvents } from "./agent-events";
import { AgentOverview } from "./agent-overview";

interface AgentDetailPageProps {
  agentId: string;
}

export function AgentDetailPage({ agentId }: AgentDetailPageProps) {
  const t = useTranslations("agentDetail");
  const tc = useTranslations("common");
  const builtinAgent = AGENT_REGISTRY[agentId];
  const { data, error, isLoading, mutate } = useControlPlaneAgent(
    agentId,
  );
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

  const status = data ? mapControlPlaneAgentStatus(data.status) : "running";
  const isOffline = status === "paused" || status === "stopped";
  const runtime: AgentRuntimeStatus = {
    agent_id: agentId,
    status,
    health: isOffline ? 0 : status === "error" ? 35 : 92,
    task_count: data ? 0 : 142,
    pending_count: data ? 0 : 8,
    error_count: status === "error" ? 1 : data ? 0 : 2,
    uptime_seconds: data ? 0 : 259200,
    last_active_at: data?.updated_at ?? new Date().toISOString(),
  };

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
              <AgentWakeupButton agentId={agentId} onWoken={() => mutate()} />
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
