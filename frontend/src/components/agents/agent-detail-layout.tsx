"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ChevronRight } from "lucide-react";
import type { AgentMeta, AgentRuntimeStatus } from "@/lib/api/types";
import { getDomainConfig } from "@/lib/registry/domains";
import { AgentAvatar } from "@/components/shared/agent-avatar";
import { AgentStatusDot } from "@/components/shared/agent-status-dot";
import { DomainBadge } from "@/components/shared/domain-badge";

interface AgentDetailLayoutProps {
  agentMeta: AgentMeta;
  runtime: AgentRuntimeStatus;
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days > 0) return `${days}d ${hours}h`;
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

export function AgentDetailLayout({
  agentMeta,
  runtime,
}: AgentDetailLayoutProps) {
  const t = useTranslations("agentDetail");
  const locale = useLocale();
  const domainConfig = getDomainConfig(agentMeta.domain);

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Link
          href={`/${locale}/agents`}
          className="hover:text-foreground transition-colors"
        >
          {t("backToFleet")}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" />
        <span style={{ color: domainConfig.color }}>{domainConfig.label}</span>
        <ChevronRight className="h-3.5 w-3.5" />
        <span className="text-foreground font-medium">{agentMeta.name}</span>
      </nav>

      {/* Header */}
      <div className="flex items-start gap-4">
        <AgentAvatar
          domain={agentMeta.domain}
          icon={agentMeta.icon}
          shortName={agentMeta.shortName}
          size="lg"
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {agentMeta.name}
            </h1>
            <DomainBadge domain={agentMeta.domain} />
          </div>
          <p className="text-muted-foreground mt-1">{agentMeta.description}</p>
        </div>

        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex items-center gap-2">
            <AgentStatusDot status={runtime.status} />
            <span className="text-sm font-medium capitalize">
              {runtime.status}
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            {t("uptime")}: {formatUptime(runtime.uptime_seconds)}
          </span>
        </div>
      </div>
    </div>
  );
}
