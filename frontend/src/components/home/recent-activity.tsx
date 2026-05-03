"use client";

import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { ArrowRight, ActivityIcon } from "lucide-react";
import { ActivityItem } from "@/components/shared/activity-item";
import type { ActivityEvent } from "@/lib/api/types";

const MOCK_EVENTS: ActivityEvent[] = [
  {
    id: "evt-001",
    agent_id: "requirement-manager",
    event_type: "requirement.extracted",
    description: "extracted requirement REQ-042 from meeting notes",
    payload: {},
    timestamp: "2026-05-03T01:58:00.000Z",
  },
  {
    id: "evt-002",
    agent_id: "requirement-manager",
    event_type: "requirement.confirmed",
    description: "confirmed requirement REQ-038",
    payload: {},
    timestamp: "2026-05-03T01:55:00.000Z",
  },
  {
    id: "evt-003",
    agent_id: "requirement-manager",
    event_type: "requirement.extracted",
    description: "extracted requirement REQ-043 from Slack thread",
    payload: {},
    timestamp: "2026-05-03T01:48:00.000Z",
  },
  {
    id: "evt-004",
    agent_id: "requirement-manager",
    event_type: "requirement.changed",
    description: "updated priority of REQ-031 to high",
    payload: {},
    timestamp: "2026-05-03T01:35:00.000Z",
  },
  {
    id: "evt-005",
    agent_id: "requirement-manager",
    event_type: "requirement.extracted",
    description: "extracted requirement REQ-044 from customer call",
    payload: {},
    timestamp: "2026-05-03T01:20:00.000Z",
  },
];

export function RecentActivity() {
  const t = useTranslations("home");
  const locale = useLocale();

  const events = MOCK_EVENTS.slice(0, 5);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight">
          {t("recentActivity")}
        </h2>
        <Link
          href={`/${locale}/activity`}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {t("viewAll")}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {events.length > 0 ? (
        <div className="rounded-xl border bg-card divide-y">
          {events.map((event) => (
            <ActivityItem key={event.id} event={event} className="px-4" />
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-xl border bg-card py-8 text-center">
          <ActivityIcon className="h-8 w-8 text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">{t("noActivity")}</p>
        </div>
      )}
    </section>
  );
}
