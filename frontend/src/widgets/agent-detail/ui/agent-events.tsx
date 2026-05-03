"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import {
  AGENT_REGISTRY,
  AgentAvatar,
  AgentDomainBadge,
} from "@/entities/agent";
import type { ActivityEvent } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface AgentEventsProps {
  agentId: string;
}

function getMockEvents(agentId: string): ActivityEvent[] {
  const now = Date.now();
  return [
    {
      id: "evt-1",
      agent_id: agentId,
      event_type: "requirement.extracted",
      description: "Extracted 3 new requirements from meeting notes",
      payload: { count: 3 },
      timestamp: new Date(now - 1000 * 60 * 15).toISOString(),
    },
    {
      id: "evt-2",
      agent_id: agentId,
      event_type: "requirement.confirmed",
      description: "Requirement REQ-042 confirmed by reviewer",
      payload: { requirement_id: "REQ-042" },
      timestamp: new Date(now - 1000 * 60 * 45).toISOString(),
    },
    {
      id: "evt-3",
      agent_id: agentId,
      event_type: "health.check",
      description: "Health check passed - all services operational",
      payload: { status: "ok" },
      timestamp: new Date(now - 1000 * 60 * 120).toISOString(),
    },
    {
      id: "evt-4",
      agent_id: agentId,
      event_type: "requirement.conflict",
      description: "Conflict detected between REQ-038 and REQ-041",
      payload: { ids: ["REQ-038", "REQ-041"] },
      timestamp: new Date(now - 1000 * 60 * 180).toISOString(),
    },
    {
      id: "evt-5",
      agent_id: agentId,
      event_type: "ingest.completed",
      description: "Ingested document: Q1 Planning Meeting",
      payload: { source: "meeting_notes" },
      timestamp: new Date(now - 1000 * 60 * 300).toISOString(),
    },
  ];
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
  const events = getMockEvents(agentId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("events")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {events.map((event) => (
            <AgentActivityItem key={event.id} event={event} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
