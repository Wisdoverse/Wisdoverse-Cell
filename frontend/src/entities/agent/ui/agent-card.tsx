"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AgentMeta, AgentRuntimeStatus } from "../model/types";
import { AgentAvatar } from "./agent-avatar";
import { AgentStatusDot } from "./agent-status-dot";

interface AgentCardProps {
  meta: AgentMeta;
  runtime: AgentRuntimeStatus;
  onClick?: () => void;
  className?: string;
}

const statusLabels: Record<string, string> = {
  running: "Running",
  idle: "Idle",
  warning: "Warning",
  error: "Error",
  stopped: "Stopped",
};

export function AgentCard({ meta, runtime, onClick, className }: AgentCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex min-h-44 flex-col gap-3 rounded-lg border bg-card p-4 text-left transition-all duration-200",
        "hover:-translate-y-0.5 hover:shadow-md",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <AgentAvatar domain={meta.domain} shortName={meta.shortName} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">{meta.name}</span>
            {meta.source === "control-plane" && (
              <Badge variant="outline" className="rounded-md">
                {meta.adapterType}
              </Badge>
            )}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <AgentStatusDot status={runtime.status} size="sm" />
            <span>{statusLabels[runtime.status]}</span>
          </div>
        </div>
      </div>

      <p className="line-clamp-2 min-h-10 text-xs text-muted-foreground">
        {meta.description}
      </p>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <div>
          <span className="font-medium text-foreground">{runtime.task_count}</span>{" "}
          tasks
        </div>
        {runtime.pending_count > 0 && (
          <div>
            <span className="font-medium text-amber-600">
              {runtime.pending_count}
            </span>{" "}
            pending
          </div>
        )}
        {runtime.error_count > 0 && (
          <div>
            <span className="font-medium text-red-600">
              {runtime.error_count}
            </span>{" "}
            errors
          </div>
        )}
      </div>

      <div className="mt-auto h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${runtime.health}%`,
            backgroundColor:
              runtime.health >= 80
                ? "var(--status-running)"
                : runtime.health >= 50
                  ? "var(--status-warning)"
                  : "var(--status-error)",
          }}
        />
      </div>
    </button>
  );
}
