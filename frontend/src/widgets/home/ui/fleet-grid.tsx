"use client";

import { useMemo } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { DOMAIN_LIST } from "@/lib/registry/domains";
import { AgentCard } from "@/entities/agent/ui/agent-display-card";
import { agentDefinitionsToMetas, useControlPlaneAgents } from "@/entities/agent";
import {
  listControlPlaneRuns,
  listControlPlaneWorkItems,
} from "@/entities/control-plane";
import {
  controlPlaneRuntimeForAgent,
  runsForAgent,
  workItemsForAgent,
} from "../model/control-plane-home";

export function FleetGrid() {
  const t = useTranslations("home");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const agentsQuery = useControlPlaneAgents({ limit: 500 });
  const runsQuery = useSWR(["home-control-plane-runs", 200], () =>
    listControlPlaneRuns({ limit: 200 }),
  );
  const workItemsQuery = useSWR(["home-control-plane-work-items", 500], () =>
    listControlPlaneWorkItems({ limit: 500 }),
  );

  const controlPlaneAgents = useMemo(
    () => agentsQuery.data?.agents ?? [],
    [agentsQuery.data?.agents],
  );
  const agentMetas = useMemo(
    () => agentDefinitionsToMetas(controlPlaneAgents),
    [controlPlaneAgents],
  );
  const agentById = new Map(controlPlaneAgents.map((agent) => [agent.agent_id, agent]));
  const runs = runsQuery.data?.runs ?? [];
  const workItems = workItemsQuery.data?.work_items ?? [];
  const isLoading = agentsQuery.isLoading || runsQuery.isLoading || workItemsQuery.isLoading;
  const hasError = agentsQuery.error || runsQuery.error || workItemsQuery.error;

  const domainsWithAgents = DOMAIN_LIST.map((domain) => {
    const agents = agentMetas.filter((agent) => agent.domain === domain.id);
    return { domain, agents };
  }).filter(({ agents }) => agents.length > 0);

  return (
    <section className="space-y-6">
      <h2 className="text-lg font-semibold tracking-tight">
        {t("agentFleet")}
      </h2>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-44 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : hasError ? (
        <p className="text-sm text-destructive">{tc("error")}</p>
      ) : domainsWithAgents.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t("noAgents")}
        </p>
      ) : (
        domainsWithAgents.map(({ domain, agents }) => (
          <div key={domain.id} className="space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">
              {domain.label}{" "}
              <span className="text-xs">({agents.length})</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {agents.map((agent, index) => {
                const definition = agentById.get(agent.id);
                if (!definition) return null;
                const runtime = controlPlaneRuntimeForAgent(
                  definition,
                  runsForAgent(runs, agent.id),
                  workItemsForAgent(workItems, agent.id),
                );
                return (
                <div
                  key={agent.id}
                  className="animate-slide-up"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <AgentCard
                    meta={agent}
                    runtime={runtime}
                    onClick={() =>
                      router.push(`/${locale}/agents/${agent.id}`)
                    }
                  />
                </div>
              )})}
            </div>
          </div>
        ))
      )}
    </section>
  );
}
