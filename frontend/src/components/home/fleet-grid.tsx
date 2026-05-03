"use client";

import { useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { DOMAIN_LIST } from "@/lib/registry/domains";
import { getAgentsByDomain, getAllAgents } from "@/lib/registry/agents";
import { AgentCard } from "@/components/shared/agent-card";
import type { AgentRuntimeStatus, AgentMeta } from "@/lib/api/types";

const MOCK_RUNTIME_LAST_ACTIVE_AT = "2026-05-03T02:00:00.000Z";

function seedRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function createMockRuntimes(agents: AgentMeta[]): Record<string, AgentRuntimeStatus> {
  const runtimes: Record<string, AgentRuntimeStatus> = {};
  agents.forEach((agent, i) => {
    runtimes[agent.id] = {
      agent_id: agent.id,
      status: "running",
      health: 85 + Math.floor(seedRandom(i + 1) * 15),
      task_count: Math.floor(seedRandom(i + 10) * 200),
      pending_count: Math.floor(seedRandom(i + 20) * 10),
      error_count: Math.floor(seedRandom(i + 30) * 3),
      uptime_seconds: 259200,
      last_active_at: MOCK_RUNTIME_LAST_ACTIVE_AT,
    };
  });
  return runtimes;
}

export function FleetGrid() {
  const t = useTranslations("home");
  const locale = useLocale();
  const router = useRouter();

  const allAgents = getAllAgents();
  const [mockRuntimes] = useState(() => createMockRuntimes(allAgents));

  const domainsWithAgents = DOMAIN_LIST.map((domain) => ({
    domain,
    agents: getAgentsByDomain(domain.id),
  })).filter(({ agents }) => agents.length > 0);

  return (
    <section className="space-y-6">
      <h2 className="text-lg font-semibold tracking-tight">
        {t("agentFleet")}
      </h2>

      {domainsWithAgents.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No agents registered yet.
        </p>
      ) : (
        domainsWithAgents.map(({ domain, agents }) => (
          <div key={domain.id} className="space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">
              {domain.label}{" "}
              <span className="text-xs">({agents.length})</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {agents.map((agent: AgentMeta, index: number) => (
                <div
                  key={agent.id}
                  className="animate-slide-up"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <AgentCard
                    meta={agent}
                    runtime={mockRuntimes[agent.id]}
                    onClick={() =>
                      router.push(`/${locale}/agents/${agent.id}`)
                    }
                  />
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </section>
  );
}
