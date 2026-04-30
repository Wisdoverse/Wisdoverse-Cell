"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/shared/page-header";
import {
  ActivityFiltersBar,
  type ActivityFilters,
} from "@/components/activity/activity-filters";
import { ActivityTimeline } from "@/components/activity/activity-timeline";
import type { ActivityEvent } from "@/lib/api/types";
import { AGENT_REGISTRY } from "@/lib/registry/agents";

const MOCK_EVENTS: ActivityEvent[] = [
  {
    id: "evt-001",
    agent_id: "requirement-manager",
    event_type: "requirement.extracted",
    description: "extracted requirement REQ-042 from meeting notes",
    payload: {},
    timestamp: new Date(Date.now() - 2 * 60000).toISOString(),
  },
  {
    id: "evt-002",
    agent_id: "requirement-manager",
    event_type: "requirement.confirmed",
    description: "confirmed requirement REQ-038",
    payload: {},
    timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
  },
  {
    id: "evt-003",
    agent_id: "requirement-manager",
    event_type: "approval.requested",
    description: "sent approval request for REQ-041",
    payload: {},
    timestamp: new Date(Date.now() - 15 * 60000).toISOString(),
  },
  {
    id: "evt-004",
    agent_id: "requirement-manager",
    event_type: "requirement.extracted",
    description: "extracted requirement REQ-040 from customer feedback",
    payload: {},
    timestamp: new Date(Date.now() - 45 * 60000).toISOString(),
  },
  {
    id: "evt-005",
    agent_id: "requirement-manager",
    event_type: "requirement.confirmed",
    description: "confirmed requirement REQ-037",
    payload: {},
    timestamp: new Date(Date.now() - 90 * 60000).toISOString(),
  },
  {
    id: "evt-006",
    agent_id: "requirement-manager",
    event_type: "requirement.extracted",
    description: "extracted 3 requirements from product review document",
    payload: {},
    timestamp: new Date(Date.now() - 25 * 3600000).toISOString(),
  },
  {
    id: "evt-007",
    agent_id: "requirement-manager",
    event_type: "requirement.rejected",
    description: "requirement REQ-035 rejected as duplicate",
    payload: {},
    timestamp: new Date(Date.now() - 26 * 3600000).toISOString(),
  },
];

export default function ActivityPage() {
  const t = useTranslations("activity");
  const [filters, setFilters] = useState<ActivityFilters>({});

  const filteredEvents = filters.domain
    ? MOCK_EVENTS.filter((event) => {
        const agentMeta = AGENT_REGISTRY[event.agent_id];
        return agentMeta?.domain === filters.domain;
      })
    : MOCK_EVENTS;

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
