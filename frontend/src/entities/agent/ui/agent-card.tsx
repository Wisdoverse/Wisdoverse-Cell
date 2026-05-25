"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/shared/ui/badge";
import { cn } from "@/lib/utils";
import type { AgentKind, AgentMeta, AgentRuntimeStatus } from "../model/types";
import { AgentAvatar } from "./agent-avatar";
import { AgentStatusDot } from "./agent-status-dot";

interface AgentCardProps {
  meta: AgentMeta;
  runtime: AgentRuntimeStatus;
  onClick?: () => void;
  className?: string;
}

export function AgentCard({ meta, runtime, onClick, className }: AgentCardProps) {
  const t = useTranslations("agents");
  const kindKey: AgentKind | "reserved" =
    meta.implemented === false
      ? "reserved"
      : meta.businessAgent
        ? "business_runtime_agent"
        : meta.agentKind
          ? meta.agentKind
          : meta.source === "control-plane"
            ? "organization_role"
            : "capability_module";
  const kindLabel =
    kindKey === "reserved" ? t("agentKindBadges.reserved") : t(`agentKindBadges.${kindKey}`);

  return (
    <button
      onClick={onClick}
      className={cn(
        "bg-card flex min-h-44 flex-col gap-3 rounded-lg border p-4 text-left transition-all duration-200",
        "hover:-translate-y-0.5 hover:shadow-md",
        "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <AgentAvatar domain={meta.domain} shortName={meta.shortName} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">{meta.name}</span>
            <Badge variant="outline" className="rounded-md">
              {kindLabel}
            </Badge>
          </div>
          <div className="text-muted-foreground mt-1 flex items-center gap-1.5 text-xs">
            <AgentStatusDot status={runtime.status} size="sm" />
            <span>{t(`statusLabels.${runtime.status}`)}</span>
          </div>
        </div>
      </div>

      <p className="text-muted-foreground line-clamp-2 min-h-10 text-xs">{meta.description}</p>

      <div className="flex flex-wrap gap-1.5">
        {meta.interactionMode && (
          <Badge variant="secondary" className="rounded-md text-[11px]">
            {t(`interactionModes.${meta.interactionMode}`)}
          </Badge>
        )}
      </div>

      <div className="text-muted-foreground flex items-center gap-4 text-xs">
        <div>
          <span className="text-foreground font-medium">{runtime.task_count}</span>{" "}
          {t("taskCount", { count: runtime.task_count })}
        </div>
        {runtime.pending_count > 0 && (
          <div>
            <span className="font-medium text-amber-600">{runtime.pending_count}</span>{" "}
            {t("pendingCount", { count: runtime.pending_count })}
          </div>
        )}
        {runtime.error_count > 0 && (
          <div>
            <span className="font-medium text-red-600">{runtime.error_count}</span>{" "}
            {t("errorCount", { count: runtime.error_count })}
          </div>
        )}
      </div>

      <div
        aria-label={t("healthLabel", { value: runtime.health })}
        className="bg-muted mt-auto h-1.5 w-full overflow-hidden rounded-full"
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
