"use client";

import { useTranslations } from "next-intl";
import type { ActivityEvent } from "@/lib/api/types";
import { ActivityItem } from "@/entities/activity";

interface ActivityTimelineProps {
  events: ActivityEvent[];
}

function groupByDate(
  events: ActivityEvent[],
  todayLabel: string,
  yesterdayLabel: string,
): Record<string, ActivityEvent[]> {
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();
  const groups: Record<string, ActivityEvent[]> = {};

  for (const event of events) {
    const dateStr = new Date(event.timestamp).toDateString();
    const label =
      dateStr === today
        ? todayLabel
        : dateStr === yesterday
          ? yesterdayLabel
          : dateStr;
    if (!groups[label]) groups[label] = [];
    groups[label].push(event);
  }

  return groups;
}

export function ActivityTimeline({ events }: ActivityTimelineProps) {
  const t = useTranslations("activity");

  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-lg font-medium text-muted-foreground">
          {t("noActivity")}
        </p>
        <p className="text-sm text-muted-foreground mt-1">
          {t("noActivityDescription")}
        </p>
      </div>
    );
  }

  const groups = groupByDate(events, t("today"), t("yesterday"));

  return (
    <div className="space-y-6">
      {Object.entries(groups).map(([label, groupEvents]) => (
        <div key={label}>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-sm font-medium text-muted-foreground">
              {label}
            </span>
            <div className="flex-1 h-px bg-border" />
          </div>
          <div className="space-y-1">
            {groupEvents.map((event) => (
              <ActivityItem key={event.id} event={event} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
