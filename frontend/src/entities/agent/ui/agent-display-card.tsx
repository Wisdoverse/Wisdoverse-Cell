"use client";

import { useTranslations } from "next-intl";

import type { AgentMeta, AgentRuntimeStatus } from "../model/types";
import { AgentAvatar } from "./agent-display-avatar";
import { AgentStatusDot } from "./agent-display-status-dot";
import { cn } from "@/lib/utils";

interface AgentCardProps {
  meta: AgentMeta;
  runtime: AgentRuntimeStatus;
  onClick?: () => void;
  className?: string;
}

export function AgentCard({ meta, runtime, onClick, className }: AgentCardProps) {
  const t = useTranslations("agents");

  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card p-4 text-left transition-all duration-200",
        "hover:-translate-y-0.5 hover:shadow-md",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className
      )}
    >
      <div className="flex items-center gap-3">
        <AgentAvatar
          domain={meta.domain}
          icon={meta.icon}
          shortName={meta.shortName}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">{meta.name}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <AgentStatusDot status={runtime.status} size="sm" />
            <span>{t(`statusLabels.${runtime.status}`)}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <div>
          <span className="font-medium text-foreground">{runtime.task_count}</span>
          {" "}{t("taskCount", { count: runtime.task_count })}
        </div>
        {runtime.pending_count > 0 && (
          <div>
            <span className="font-medium text-amber-600">{runtime.pending_count}</span>
            {" "}{t("pendingCount", { count: runtime.pending_count })}
          </div>
        )}
        {runtime.error_count > 0 && (
          <div>
            <span className="font-medium text-red-600">{runtime.error_count}</span>
            {" "}{t("errorCount", { count: runtime.error_count })}
          </div>
        )}
      </div>

      <div
        aria-label={t("healthLabel", { value: runtime.health })}
        className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
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
