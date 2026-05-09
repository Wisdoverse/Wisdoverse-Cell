"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";

import {
  ActivityFiltersBar,
  type ActivityFilters,
} from "./activity-filters";
import { ActivityTimeline } from "./activity-timeline";
import { PageHeader } from "@/shared/ui/page-header";
import { controlPlaneRunsToActivityEvents } from "@/entities/activity";
import { listControlPlaneRuns } from "@/entities/control-plane";
import { AGENT_REGISTRY } from "@/entities/agent";

export function ActivityPageWidget() {
  const t = useTranslations("activity");
  const [filters, setFilters] = useState<ActivityFilters>({});
  const { data, error, isLoading } = useSWR(["activity-control-plane-runs"], () =>
    listControlPlaneRuns({ limit: 100 }),
  );

  const events = controlPlaneRunsToActivityEvents(data?.runs ?? [], (run) =>
    t("runEvent", { runId: run.run_id, status: run.status }),
  );
  const filteredEvents = filters.domain
    ? events.filter((event) => {
        const agentMeta = AGENT_REGISTRY[event.agent_id];
        return agentMeta?.domain === filters.domain;
      })
    : events;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <ActivityFiltersBar filters={filters} onFiltersChange={setFilters} />
        }
      />
      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t("loading")}</p>
      ) : error ? (
        <p className="text-sm text-destructive">{t("loadError")}</p>
      ) : (
        <ActivityTimeline events={filteredEvents} />
      )}
    </div>
  );
}
