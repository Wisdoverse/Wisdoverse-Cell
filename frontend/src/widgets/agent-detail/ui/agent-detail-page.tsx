"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";

import {
  AGENT_REGISTRY,
  agentDefinitionToMeta,
  useControlPlaneAgent,
  type AgentRuntimeStatus,
  type AgentStatus,
} from "@/entities/agent";
import { AgentWakeupButton } from "@/features/agent-wakeup";
import { AgentConfig } from "./agent-config";
import { AgentDetailLayout } from "./agent-detail-layout";
import { AgentEvents } from "./agent-events";
import { AgentOverview } from "./agent-overview";

interface AgentDetailPageProps {
  agentId: string;
}

function mapControlPlaneStatus(status: string): AgentStatus {
  const normalized = status.toLowerCase();
  if (normalized === "running") return "running";
  if (normalized === "error") return "error";
  if (normalized === "paused" || normalized === "terminated") return "stopped";
  return "idle";
}

export function AgentDetailPage({ agentId }: AgentDetailPageProps) {
  const t = useTranslations("agentDetail");
  const tc = useTranslations("common");
  const builtinAgent = AGENT_REGISTRY[agentId];
  const { data, error, isLoading, mutate } = useControlPlaneAgent(
    builtinAgent ? undefined : agentId,
  );

  const agentMeta = useMemo(
    () => builtinAgent ?? (data ? agentDefinitionToMeta(data) : undefined),
    [builtinAgent, data],
  );

  if (!agentMeta && isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <p>{tc("loading")}</p>
      </div>
    );
  }

  if (!agentMeta || error) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <p>{t("notFound")}</p>
      </div>
    );
  }

  const status = data ? mapControlPlaneStatus(data.status) : "running";
  const runtime: AgentRuntimeStatus = {
    agent_id: agentId,
    status,
    health: status === "stopped" ? 0 : status === "error" ? 35 : 92,
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
          agentMeta.source === "control-plane" ? (
            <AgentWakeupButton agentId={agentId} onWoken={() => mutate()} />
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
