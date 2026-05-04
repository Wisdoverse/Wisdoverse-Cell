"use client";

import { useTranslations } from "next-intl";

import { FleetGrid } from "@/components/home/fleet-grid";
import { GreetingBanner } from "@/components/home/greeting-banner";
import { PendingApprovals } from "@/components/home/pending-approvals";
import { RecentActivity } from "@/components/home/recent-activity";
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
