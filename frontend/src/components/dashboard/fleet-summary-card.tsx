"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { ArrowRight } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/shared/ui/card";
import { AgentStatusDot } from "@/components/shared/agent-status-dot";
import { getAllAgents } from "@/lib/registry/agents";
import type { AgentStatus } from "@/lib/api/types";

interface FleetCounts {
  total: number;
  running: number;
  idle: number;
  error: number;
}

function generateMockCounts(total: number): FleetCounts {
  const running = Math.max(1, Math.floor(total * 0.6));
  const error = total >= 3 ? 1 : 0;
  const idle = total - running - error;

  return { total, running, idle: Math.max(0, idle), error };
}

const badges: { key: keyof Omit<FleetCounts, "total">; status: AgentStatus }[] = [
  { key: "running", status: "running" },
  { key: "idle", status: "idle" },
  { key: "error", status: "error" },
];

export function FleetSummaryCard() {
  const t = useTranslations("dashboard");
  const locale = useLocale();

  const agents = getAllAgents();
  const [counts] = useState(() => generateMockCounts(agents.length));

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
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-lg border p-3 text-center">
            <p className="text-sm text-muted-foreground">{t("fleetTotal")}</p>
            <p className="text-2xl font-bold">{counts.total}</p>
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
