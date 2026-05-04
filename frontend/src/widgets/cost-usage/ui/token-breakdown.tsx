"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { AgentAvatar } from "@/entities/agent/ui/agent-display-avatar";
import { getAllAgents } from "@/lib/registry/agents";
import type { AgentMeta } from "@/lib/api/types";

interface TokenBreakdownProps {
  period: string;
}

function seedRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function periodSeed(period: string): number {
  return Array.from(period).reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

function generateTokenData(agents: AgentMeta[], period: string) {
  const seed = periodSeed(period);
  return agents.map((agent, i) => ({
    agent,
    tokens: Math.floor(seedRandom(seed + i + 1) * 5_000_000) + 500_000,
    cost: Math.round((seedRandom(seed + i + 100) * 400 + 50) * 100) / 100,
  })).sort((a, b) => b.tokens - a.tokens);
}

export function TokenBreakdown({ period }: TokenBreakdownProps) {
  const agents = getAllAgents();
  const data = useMemo(() => generateTokenData(agents, period), [agents, period]);
  const totalTokens = data.reduce((s, d) => s + d.tokens, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Token Usage by Agent</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Header */}
          <div className="grid grid-cols-[1fr_100px_80px_60px] gap-2 text-xs font-medium text-muted-foreground pb-2 border-b">
            <span>Agent</span>
            <span className="text-right">Tokens</span>
            <span className="text-right">Cost</span>
            <span className="text-right">%</span>
          </div>
          {data.map((row) => (
            <div key={row.agent.id} className="grid grid-cols-[1fr_100px_80px_60px] gap-2 items-center text-sm">
              <div className="flex items-center gap-2 min-w-0">
                <AgentAvatar
                  domain={row.agent.domain}
                  icon={row.agent.icon}
                  shortName={row.agent.shortName}
                  size="sm"
                />
                <span className="truncate">{row.agent.name}</span>
              </div>
              <span className="text-right text-muted-foreground">
                {(row.tokens / 1000).toFixed(0)}k
              </span>
              <span className="text-right">${row.cost.toFixed(2)}</span>
              <span className="text-right text-muted-foreground">
                {((row.tokens / totalTokens) * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
