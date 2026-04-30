"use client";

import { useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { DOMAIN_LIST } from "@/lib/registry/domains";
import { getAgentsByDomain, getAllAgents } from "@/lib/registry/agents";
import { AgentCard } from "@/components/shared/agent-card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { AgentRuntimeStatus, AgentMeta } from "@/lib/api/types";
import type { FleetFiltersState } from "./fleet-filters";

interface FleetOverviewProps {
  filters: FleetFiltersState;
}

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
      last_active_at: new Date().toISOString(),
    };
  });
  return runtimes;
}

export function FleetOverview({ filters }: FleetOverviewProps) {
  const t = useTranslations("agents");
  const locale = useLocale();
  const router = useRouter();

  const allRegisteredAgents = getAllAgents();
  const [mockRuntimes] = useState(() => createMockRuntimes(allRegisteredAgents));

  function getRuntime(agentId: string): AgentRuntimeStatus {
    return mockRuntimes[agentId];
  }

  function filterAgents(agents: AgentMeta[]): AgentMeta[] {
    return agents.filter((agent) => {
      // Status filter
      if (filters.status !== "all") {
        const runtime = getRuntime(agent.id);
        if (runtime.status !== filters.status) return false;
      }

      // Search filter
      if (filters.search) {
        const query = filters.search.toLowerCase();
        const matchesName = agent.name.toLowerCase().includes(query);
        const matchesId = agent.id.toLowerCase().includes(query);
        const matchesDescription = agent.description
          .toLowerCase()
          .includes(query);
        if (!matchesName && !matchesId && !matchesDescription) return false;
      }

      return true;
    });
  }

  return (
    <div className="space-y-4">
      {DOMAIN_LIST.map((domain) => {
        const allAgents = getAgentsByDomain(domain.id);
        const filteredAgents = filterAgents(allAgents);
        const runningCount = allAgents.filter(
          (a) => getRuntime(a.id).status === "running"
        ).length;

        return (
          <Collapsible key={domain.id} defaultOpen>
            <div className="rounded-lg border">
              <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/50 transition-colors">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold">{domain.label}</h3>
                  <span className="text-xs text-muted-foreground">
                    ({runningCount}/{allAgents.length} running)
                  </span>
                </div>
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform duration-200 [[data-state=closed]_&]:rotate-[-90deg]" />
              </CollapsibleTrigger>

              <CollapsibleContent>
                <div className="px-4 pb-4">
                  {filteredAgents.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                      {filteredAgents.map((agent: AgentMeta, index: number) => (
                        <div
                          key={agent.id}
                          className="animate-slide-up"
                          style={{ animationDelay: `${index * 50}ms` }}
                        >
                          <AgentCard
                            meta={agent}
                            runtime={getRuntime(agent.id)}
                            onClick={() =>
                              router.push(`/${locale}/agents/${agent.id}`)
                            }
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="py-6 text-center text-sm text-muted-foreground">
                      {t("noAgents")}
                    </p>
                  )}
                </div>
              </CollapsibleContent>
            </div>
          </Collapsible>
        );
      })}
    </div>
  );
}
