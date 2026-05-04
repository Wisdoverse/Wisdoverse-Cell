"use client";

import { useTranslations } from "next-intl";

import { FleetGrid } from "./fleet-grid";
import { GreetingBanner } from "./greeting-banner";
import { PendingApprovals } from "./pending-approvals";
import { RecentActivity } from "./recent-activity";
import { PageHeader } from "@/shared/ui/page-header";

export function HomePageWidget() {
  const t = useTranslations("home");

  return (
    <div className="space-y-8">
      <PageHeader title={t("title")} />
      <GreetingBanner />
      <PendingApprovals />
      <FleetGrid />
      <RecentActivity />
    </div>
  );
}
