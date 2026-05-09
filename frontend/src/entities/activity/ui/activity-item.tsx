import type { ActivityEvent } from "@/lib/api/types";
import { AgentDisplayAvatar, AGENT_REGISTRY, DomainBadge } from "@/entities/agent";
import { cn } from "@/lib/utils";

interface ActivityItemProps {
  event: ActivityEvent;
  className?: string;
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ActivityItem({ event, className }: ActivityItemProps) {
  const agentMeta = AGENT_REGISTRY[event.agent_id];

  return (
    <div className={cn("flex items-start gap-3 py-2", className)}>
      {agentMeta ? (
        <AgentDisplayAvatar
          domain={agentMeta.domain}
          icon={agentMeta.icon}
          shortName={agentMeta.shortName}
          size="sm"
        />
      ) : (
        <div className="h-8 w-8 rounded-xl bg-muted flex items-center justify-center text-xs">
          ?
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className="text-sm">
          <span className="font-medium">{agentMeta?.name ?? event.agent_id}</span>
          {" "}
          <span className="text-muted-foreground">{event.description}</span>
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs text-muted-foreground">
            {formatTime(event.timestamp)}
          </span>
          {agentMeta && <DomainBadge domain={agentMeta.domain} />}
        </div>
      </div>
    </div>
  );
}
