"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import {
  AGENT_REGISTRY,
  AgentAvatar,
  AgentDomainBadge,
} from "@/entities/agent";
import { useControlPlaneRuns } from "@/entities/control-plane";
import { controlPlaneRunsToActivityEvents } from "@/entities/activity/model/control-plane-events";
import type { ActivityEvent } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface AgentEventsProps {
  agentId: string;
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function AgentActivityItem({ event }: { event: ActivityEvent }) {
  const agentMeta = AGENT_REGISTRY[event.agent_id];

  return (
    <div className={cn("flex items-start gap-3 py-2")}>
      {agentMeta ? (
        <AgentAvatar
          domain={agentMeta.domain}
          shortName={agentMeta.shortName}
          size="sm"
        />
      ) : (
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-xs">
          ?
        </div>
      )}

      <div className="min-w-0 flex-1">
        <p className="text-sm">
          <span className="font-medium">{agentMeta?.name ?? event.agent_id}</span>{" "}
          <span className="text-muted-foreground">{event.description}</span>
        </p>
        <div className="mt-0.5 flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {formatTime(event.timestamp)}
          </span>
          {agentMeta && <AgentDomainBadge domain={agentMeta.domain} />}
        </div>
      </div>
    </div>
  );
}

export function AgentEvents({ agentId }: AgentEventsProps) {
  const t = useTranslations("agentDetail");
  const { data, error, isLoading } = useControlPlaneRuns({
    agent_id: agentId,
    limit: 50,
  });
  const events = controlPlaneRunsToActivityEvents(data?.runs ?? [], (run) =>
    t("runEvent", { runId: run.run_id, status: run.status }),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("events")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t("loadingEvents")}</p>
        ) : error ? (
          <p className="text-sm text-destructive">{t("eventsLoadError")}</p>
        ) : events.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noEvents")}</p>
        ) : (
          <div className="divide-y">
            {events.map((event) => (
              <AgentActivityItem key={event.id} event={event} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
