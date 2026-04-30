"use client";

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AGENT_REGISTRY } from "@/lib/registry/agents";
import type { AgentRuntimeStatus } from "@/lib/api/types";
import { AgentDetailLayout } from "@/components/agents/agent-detail-layout";
import { AgentOverview } from "@/components/agents/agent-overview";
import { AgentEvents } from "@/components/agents/agent-events";
import { AgentConfig } from "@/components/agents/agent-config";

export default function AgentDetailPage() {
  const t = useTranslations("agentDetail");
  const params = useParams<{ agentId: string }>();
  const agentId = params.agentId;
  const agentMeta = AGENT_REGISTRY[agentId];

  if (!agentMeta) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <p>{t("notFound")}</p>
      </div>
    );
  }

  const mockRuntime: AgentRuntimeStatus = {
    agent_id: agentId,
    status: "running",
    health: 92,
    task_count: 142,
    pending_count: 8,
    error_count: 2,
    uptime_seconds: 259200,
    last_active_at: new Date().toISOString(),
  };

  return (
    <div className="space-y-6">
      <AgentDetailLayout agentMeta={agentMeta} runtime={mockRuntime} />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t("overview")}</TabsTrigger>
          <TabsTrigger value="events">{t("events")}</TabsTrigger>
          <TabsTrigger value="config">{t("config")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <AgentOverview agentMeta={agentMeta} runtime={mockRuntime} />
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
