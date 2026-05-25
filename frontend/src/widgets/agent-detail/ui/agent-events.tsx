"use client";

import { useLocale, useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { AGENT_REGISTRY, AgentAvatar, AgentDomainBadge } from "@/entities/agent";
import { useControlPlaneRuns } from "@/entities/control-plane";
import { controlPlaneRunsToActivityEvents } from "@/entities/activity";
import type { ActivityEvent } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface AgentEventsProps {
  agentId: string;
}

function formatTime(dateStr: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateStr));
}

function AgentActivityItem({ event }: { event: ActivityEvent }) {
  const agentMeta = AGENT_REGISTRY[event.agent_id];
  const locale = useLocale();

  return (
    <div className={cn("flex items-start gap-3 py-2")}>
      {agentMeta ? (
        <AgentAvatar domain={agentMeta.domain} shortName={agentMeta.shortName} size="sm" />
      ) : (
        <div className="bg-muted flex h-8 w-8 items-center justify-center rounded-lg text-xs">
          ?
        </div>
      )}

      <div className="min-w-0 flex-1">
        <p className="text-sm">
          <span className="font-medium">{agentMeta?.name ?? event.agent_id}</span>{" "}
          <span className="text-muted-foreground">{event.description}</span>
        </p>
        <div className="mt-0.5 flex items-center gap-2">
          <span className="text-muted-foreground text-xs">
            {formatTime(event.timestamp, locale)}
          </span>
          {agentMeta && <AgentDomainBadge domain={agentMeta.domain} />}
        </div>
      </div>
    </div>
  );
}

export function AgentEvents({ agentId }: AgentEventsProps) {
  const t = useTranslations("agentDetail");
  const ta = useTranslations("activity");
  const { data, error, isLoading } = useControlPlaneRuns({
    agent_id: agentId,
    limit: 50,
  });
  const events = controlPlaneRunsToActivityEvents(data?.runs ?? [], (run) =>
    t("runEvent", {
      runId: run.run_id,
      status: ta(`runStatuses.${run.status}`),
    }),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("events")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-muted-foreground text-sm">{t("loadingEvents")}</p>
        ) : error ? (
          <p className="text-destructive text-sm">{t("eventsLoadError")}</p>
        ) : events.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noEvents")}</p>
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
