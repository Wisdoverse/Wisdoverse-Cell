"use client";

import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { ArrowRight, ActivityIcon } from "lucide-react";
import {
  ActivityItem,
  controlPlaneRunsToActivityEvents,
} from "@/entities/activity";
import useSWR from "swr";

import { listControlPlaneRuns } from "@/entities/control-plane";

export function RecentActivity() {
  const t = useTranslations("home");
  const ta = useTranslations("activity");
  const locale = useLocale();
  const { data } = useSWR(["recent-control-plane-runs", 5], () =>
    listControlPlaneRuns({ limit: 5 }),
  );

  const events = controlPlaneRunsToActivityEvents(data?.runs ?? [], (run) =>
    ta("runEvent", { runId: run.run_id, status: run.status }),
  );

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
