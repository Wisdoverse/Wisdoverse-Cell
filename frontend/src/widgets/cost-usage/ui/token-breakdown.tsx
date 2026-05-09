"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { AgentDisplayAvatar, AGENT_REGISTRY } from "@/entities/agent";
import type { LLMUsageResponse } from "@/lib/api/types";

interface TokenBreakdownProps {
  data: LLMUsageResponse[];
  isLoading: boolean;
}

function aggregateByAgent(data: LLMUsageResponse[]) {
  const rows = new Map<
    string,
    { agentId: string; tokens: number; cost: number; calls: number }
  >();
  for (const day of data) {
    for (const [agentId, usage] of Object.entries(day.by_agent ?? {})) {
      const existing = rows.get(agentId) ?? {
        agentId,
        tokens: 0,
        cost: 0,
        calls: 0,
      };
      existing.tokens += usage.input_tokens + usage.output_tokens;
      existing.cost += usage.cost_usd;
      existing.calls += usage.calls;
      rows.set(agentId, existing);
    }
  }
  return [...rows.values()].sort((a, b) => b.tokens - a.tokens);
}

export function TokenBreakdown({ data, isLoading }: TokenBreakdownProps) {
  const t = useTranslations("costUsage");
  const rows = useMemo(() => aggregateByAgent(data), [data]);
  const totalTokens = rows.reduce((s, d) => s + d.tokens, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("tokenUsageByAgent")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-8 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            {t("noTokenData")}
          </div>
        ) : (
        <div className="space-y-3">
          {/* Header */}
          <div className="grid grid-cols-[1fr_100px_80px_60px] gap-2 text-xs font-medium text-muted-foreground pb-2 border-b">
            <span>{t("agent")}</span>
            <span className="text-right">{t("tokens")}</span>
            <span className="text-right">{t("cost")}</span>
            <span className="text-right">%</span>
          </div>
          {rows.map((row) => {
            const agent = AGENT_REGISTRY[row.agentId];
            return (
            <div key={row.agentId} className="grid grid-cols-[1fr_100px_80px_60px] gap-2 items-center text-sm">
              <div className="flex items-center gap-2 min-w-0">
                {agent && (
                  <AgentDisplayAvatar
                    domain={agent.domain}
                    icon={agent.icon}
                    shortName={agent.shortName}
                    size="sm"
                  />
                )}
                <span className="truncate">{agent?.name ?? row.agentId}</span>
              </div>
              <span className="text-right text-muted-foreground">
                {(row.tokens / 1000).toFixed(0)}k
              </span>
              <span className="text-right">${row.cost.toFixed(2)}</span>
              <span className="text-right text-muted-foreground">
                {totalTokens > 0 ? ((row.tokens / totalTokens) * 100).toFixed(0) : 0}%
              </span>
            </div>
          )})}
        </div>
        )}
      </CardContent>
    </Card>
  );
}
