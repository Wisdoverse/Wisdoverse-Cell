"use client";

import { useTranslations } from "next-intl";
import useSWR from "swr";

import { StatCard } from "@/shared/ui/stat-card";
import { useControlPlaneAgents } from "@/entities/agent";
import {
  listControlPlaneApprovals,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
} from "@/entities/control-plane";
import {
  controlPlaneRuntimeForAgent,
  countOpenWorkItems,
  runsForAgent,
  workItemsForAgent,
} from "../model/control-plane-home";

function getGreetingKey(): "morning" | "afternoon" | "evening" {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

export function GreetingBanner() {
  const t = useTranslations("home");
  const agentsQuery = useControlPlaneAgents({ limit: 500 });
  const approvalsQuery = useSWR(["home-control-plane-approvals", "pending"], () =>
    listControlPlaneApprovals({ status: "pending", limit: 200 }),
  );
  const runsQuery = useSWR(["home-control-plane-runs", 200], () =>
    listControlPlaneRuns({ limit: 200 }),
  );
  const workItemsQuery = useSWR(["home-control-plane-work-items", 500], () =>
    listControlPlaneWorkItems({ limit: 500 }),
  );

  const isLoading =
    agentsQuery.isLoading ||
    approvalsQuery.isLoading ||
    runsQuery.isLoading ||
    workItemsQuery.isLoading;
  const agents = agentsQuery.data?.agents ?? [];
  const pendingApprovals = approvalsQuery.data?.approvals ?? [];
  const runs = runsQuery.data?.runs ?? [];
  const workItems = workItemsQuery.data?.work_items ?? [];

  const runtimes = agents.map((agent) =>
    controlPlaneRuntimeForAgent(
      agent,
      runsForAgent(runs, agent.agent_id),
      workItemsForAgent(workItems, agent.agent_id),
    ),
  );
  const runningCount = runtimes.filter((runtime) => runtime.status === "running").length;
  const attentionCount = countOpenWorkItems(workItems) + pendingApprovals.length;
  const errorCount = runtimes.reduce((total, runtime) => total + runtime.error_count, 0);
  const pendingCount = pendingApprovals.length;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">
        {t(`greeting.${getGreetingKey()}`)}
      </h2>

      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label={t("stats.running")}
            value={runningCount}
            className="text-green-600"
          />
          <StatCard
            label={t("stats.attention")}
            value={attentionCount}
            className="text-amber-600"
          />
          <StatCard
            label={t("stats.errors")}
            value={errorCount}
            className="text-red-600"
          />
          <StatCard
            label={t("stats.pendingApprovals")}
            value={pendingCount}
            className="text-indigo-600"
          />
        </div>
      )}
    </div>
  );
}
