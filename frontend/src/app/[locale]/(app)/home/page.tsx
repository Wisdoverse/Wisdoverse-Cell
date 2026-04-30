"use client";

import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/shared/page-header";
import { GreetingBanner } from "@/components/home/greeting-banner";
import { PendingApprovals } from "@/components/home/pending-approvals";
import { FleetGrid } from "@/components/home/fleet-grid";
import { RecentActivity } from "@/components/home/recent-activity";

export default function HomePage() {
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
