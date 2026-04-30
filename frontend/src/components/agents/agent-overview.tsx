"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  HeartPulse,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AgentMeta, AgentRuntimeStatus } from "@/lib/api/types";
import { AGENT_REGISTRY } from "@/lib/registry/agents";
import { AgentAvatar } from "@/components/shared/agent-avatar";

interface AgentOverviewProps {
  agentMeta: AgentMeta;
  runtime: AgentRuntimeStatus;
}

export function AgentOverview({ agentMeta, runtime }: AgentOverviewProps) {
  const t = useTranslations("agentDetail");
  const locale = useLocale();

  const stats = [
    {
      label: t("processed"),
      value: runtime.task_count,
      icon: CheckCircle2,
      color: "text-green-600",
    },
    {
      label: t("pending"),
      value: runtime.pending_count,
      icon: Clock,
      color: "text-amber-600",
    },
    {
      label: t("errors"),
      value: runtime.error_count,
      icon: AlertTriangle,
      color: "text-red-600",
    },
    {
      label: t("health"),
      value: `${runtime.health}%`,
      icon: HeartPulse,
      color: "text-blue-600",
    },
  ];

  const upstreamAgents = agentMeta.upstream
    .map((id) => AGENT_REGISTRY[id])
    .filter(Boolean);
  const downstreamAgents = agentMeta.downstream
    .map((id) => AGENT_REGISTRY[id])
    .filter(Boolean);
  const hasConnections = upstreamAgents.length > 0 || downstreamAgents.length > 0;

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="pt-0">
              <div className="flex items-center gap-3">
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
                <div>
                  <p className="text-2xl font-bold">{stat.value}</p>
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Connected Agents */}
      <Card>
        <CardHeader>
          <CardTitle>{t("connectedAgents")}</CardTitle>
        </CardHeader>
        <CardContent>
          {!hasConnections ? (
            <p className="text-sm text-muted-foreground">{t("noConnections")}</p>
          ) : (
            <div className="space-y-4">
              {upstreamAgents.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">
                    {t("upstream")}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {upstreamAgents.map((agent) => (
                      <Link
                        key={agent.id}
                        href={`/${locale}/agents/${agent.id}`}
                        className="flex items-center gap-2 rounded-lg border px-3 py-2 hover:bg-muted transition-colors"
                      >
                        <AgentAvatar
                          domain={agent.domain}
                          icon={agent.icon}
                          shortName={agent.shortName}
                          size="sm"
                        />
                        <span className="text-sm font-medium">
                          {agent.name}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
              {downstreamAgents.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">
                    {t("downstream")}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {downstreamAgents.map((agent) => (
                      <Link
                        key={agent.id}
                        href={`/${locale}/agents/${agent.id}`}
                        className="flex items-center gap-2 rounded-lg border px-3 py-2 hover:bg-muted transition-colors"
                      >
                        <AgentAvatar
                          domain={agent.domain}
                          icon={agent.icon}
                          shortName={agent.shortName}
                          size="sm"
                        />
                        <span className="text-sm font-medium">
                          {agent.name}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
