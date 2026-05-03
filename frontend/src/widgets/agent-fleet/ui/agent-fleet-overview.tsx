"use client";

import { ChevronDown } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import {
  AgentCard,
  DOMAIN_LIST,
  type AgentMeta,
  type AgentRuntimeStatus,
} from "@/entities/agent";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/ui/collapsible";
import type { AgentFleetFiltersState } from "./agent-fleet-filters";

interface AgentFleetOverviewProps {
  agents: AgentMeta[];
  runtimes: Record<string, AgentRuntimeStatus>;
  filters: AgentFleetFiltersState;
}

const kindOrder: Record<string, number> = {
  organization_role: 0,
  integration_gateway: 1,
  capability_module: 2,
  system_worker: 3,
};

export function AgentFleetOverview({
  agents,
  runtimes,
  filters,
}: AgentFleetOverviewProps) {
  const t = useTranslations("agents");
  const locale = useLocale();
  const router = useRouter();

  function matchesFilters(agent: AgentMeta): boolean {
    const runtime = runtimes[agent.id];
    if (filters.status !== "all" && runtime?.status !== filters.status) {
      return false;
    }
    if (filters.agentKind !== "all" && agent.agentKind !== filters.agentKind) {
      return false;
    }

    const query = filters.search.trim().toLowerCase();
    if (!query) return true;

    return [
      agent.name,
      agent.id,
      agent.description,
      agent.role,
      agent.title,
      agent.agentKind,
      agent.interactionMode,
      agent.adapterType,
    ]
      .filter(Boolean)
      .some((value) => value!.toLowerCase().includes(query));
  }

  return (
    <div className="space-y-4">
      {DOMAIN_LIST.map((domain) => {
        const allAgents = agents.filter((agent) => agent.domain === domain.id);
        const filteredAgents = allAgents.filter(matchesFilters).sort((a, b) => {
          const aOrder = kindOrder[a.agentKind ?? "capability_module"] ?? 9;
          const bOrder = kindOrder[b.agentKind ?? "capability_module"] ?? 9;
          return aOrder - bOrder || a.name.localeCompare(b.name);
        });
        const runningCount = allAgents.filter(
          (agent) => runtimes[agent.id]?.status === "running",
        ).length;

        if (allAgents.length === 0 && filters.search) return null;

        return (
          <Collapsible key={domain.id} defaultOpen>
            <div className="rounded-lg border">
              <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold">{domain.label}</h3>
                  <span className="text-xs text-muted-foreground">
                    ({runningCount}/{allAgents.length} {t("running")})
                  </span>
                </div>
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform duration-200 [[data-state=closed]_&]:rotate-[-90deg]" />
              </CollapsibleTrigger>

              <CollapsibleContent>
                <div className="px-4 pb-4">
                  {filteredAgents.length > 0 ? (
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                      {filteredAgents.map((agent) => (
                        <AgentCard
                          key={agent.id}
                          meta={agent}
                          runtime={runtimes[agent.id]}
                          onClick={() =>
                            router.push(`/${locale}/agents/${agent.id}`)
                          }
                        />
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
