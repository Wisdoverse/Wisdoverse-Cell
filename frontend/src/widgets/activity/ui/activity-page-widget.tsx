"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import {
  ActivityFiltersBar,
  type ActivityFilters,
} from "@/components/activity/activity-filters";
import { ActivityTimeline } from "@/components/activity/activity-timeline";
import { PageHeader } from "@/components/shared/page-header";
import { MOCK_ACTIVITY_EVENTS } from "@/entities/activity/model/mock-events";
import { AGENT_REGISTRY } from "@/lib/registry/agents";

export function ActivityPageWidget() {
  const t = useTranslations("activity");
  const [filters, setFilters] = useState<ActivityFilters>({});

  const filteredEvents = filters.domain
    ? MOCK_ACTIVITY_EVENTS.filter((event) => {
        const agentMeta = AGENT_REGISTRY[event.agent_id];
        return agentMeta?.domain === filters.domain;
      })
    : MOCK_ACTIVITY_EVENTS;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <ActivityFiltersBar filters={filters} onFiltersChange={setFilters} />
        }
      />
      <ActivityTimeline events={filteredEvents} />
    </div>
  );
}
