"use client";

import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { ArrowRight } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/shared/ui/card";
import { AgentStatusDot } from "@/entities/agent/ui/agent-display-status-dot";
import { useAgents } from "@/entities/agent";
import type { AgentStatus } from "@/lib/api/types";

interface FleetCounts {
  total: number;
  running: number;
  idle: number;
  error: number;
  stopped: number;
}

const badges: { key: keyof Omit<FleetCounts, "total">; status: AgentStatus }[] = [
  { key: "running", status: "running" },
  { key: "idle", status: "idle" },
  { key: "error", status: "error" },
  { key: "stopped", status: "stopped" },
];

export function FleetSummaryCard() {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const { data, isLoading } = useAgents();

  const counts = (data?.agents ?? []).reduce<FleetCounts>(
    (next, agent) => {
      next.total += 1;
      if (agent.status === "running") next.running += 1;
      else if (agent.status === "error") next.error += 1;
      else if (agent.status === "stopped") next.stopped += 1;
      else next.idle += 1;
      return next;
    },
    { total: 0, running: 0, idle: 0, error: 0, stopped: 0 },
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{t("fleetTitle")}</span>
          <Link
            href={`/${locale}/agents`}
            className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            {t("fleetViewAll")}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <div className="rounded-lg border p-3 text-center">
            <p className="text-sm text-muted-foreground">{t("fleetTotal")}</p>
            <p className="text-2xl font-bold">{isLoading ? "--" : counts.total}</p>
          </div>
          {badges.map(({ key, status }) => (
            <div key={key} className="rounded-lg border p-3 text-center">
              <div className="flex items-center justify-center gap-1.5">
                <AgentStatusDot status={status} size="sm" />
                <p className="text-sm text-muted-foreground">
                  {t(`fleet_${key}`)}
                </p>
              </div>
              <p className="text-2xl font-bold">{counts[key]}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
