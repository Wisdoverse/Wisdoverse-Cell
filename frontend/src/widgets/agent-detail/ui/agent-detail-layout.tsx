"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ChevronRight } from "lucide-react";
import {
  AgentAvatar,
  AgentDomainBadge,
  AgentStatusDot,
  getDomainConfig,
  getDomainLabelKey,
  type AgentMeta,
  type AgentRuntimeStatus,
} from "@/entities/agent";

interface AgentDetailLayoutProps {
  agentMeta: AgentMeta;
  runtime: AgentRuntimeStatus;
  actions?: ReactNode;
}

function formatUptime(
  seconds: number,
  t: (key: string, values: Record<string, number>) => string,
): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days > 0) return t("uptimeDaysHours", { days, hours });
  const minutes = Math.floor((seconds % 3600) / 60);
  return t("uptimeHoursMinutes", { hours, minutes });
}

export function AgentDetailLayout({ agentMeta, runtime, actions }: AgentDetailLayoutProps) {
  const t = useTranslations("agentDetail");
  const ta = useTranslations("agents");
  const locale = useLocale();
  const domainConfig = getDomainConfig(agentMeta.domain);

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <nav className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Link href={`/${locale}/agents`} className="hover:text-foreground transition-colors">
          {t("backToFleet")}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" />
        <span style={{ color: domainConfig.color }}>
          {ta(`domainLabels.${getDomainLabelKey(agentMeta.domain)}`)}
        </span>
        <ChevronRight className="h-3.5 w-3.5" />
        <span className="text-foreground font-medium">{agentMeta.name}</span>
      </nav>

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <AgentAvatar domain={agentMeta.domain} shortName={agentMeta.shortName} size="lg" />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{agentMeta.name}</h1>
            <AgentDomainBadge domain={agentMeta.domain} />
          </div>
          <p className="text-muted-foreground mt-1">{agentMeta.description}</p>
        </div>

        <div className="flex shrink-0 flex-col gap-3 sm:items-end">
          {actions}
          <div className="flex items-center gap-2">
            <AgentStatusDot status={runtime.status} />
            <span className="text-sm font-medium">{ta(`statusLabels.${runtime.status}`)}</span>
          </div>
          <span className="text-muted-foreground text-xs">
            {t("uptime")}: {formatUptime(runtime.uptime_seconds, t)}
          </span>
        </div>
      </div>
    </div>
  );
}
