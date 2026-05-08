"use client";

import { useTranslations } from "next-intl";
import { StatCard } from "@/shared/ui/stat-card";
import { useAgents } from "@/entities/agent/model/use-agents";
import { useApprovals } from "@/entities/approval/model/use-approvals";

function getGreetingKey(): "morning" | "afternoon" | "evening" {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

export function GreetingBanner() {
  const t = useTranslations("home");
  const { data: agentData, isLoading: agentsLoading } = useAgents();
  const { data: approvalData, isLoading: approvalsLoading } = useApprovals({
    status: "pending",
  });

  const isLoading = agentsLoading || approvalsLoading;
  const agents = agentData?.agents ?? [];
  const pendingApprovals = approvalData?.approvals ?? [];

  const runningCount = agents.filter((a) => a.status === "running").length;
  const attentionCount = agents.filter(
    (a) =>
      a.status === "warning" || a.status === "idle" || a.status === "paused",
  ).length;
  const errorCount = agents.filter((a) => a.status === "error").length;
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
