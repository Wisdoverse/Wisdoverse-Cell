"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/shared/page-header";
import { FleetFilters } from "@/components/agents/fleet-filters";
import { FleetOverview } from "@/components/agents/fleet-overview";
import type { FleetFiltersState } from "@/components/agents/fleet-filters";

export default function AgentsPage() {
  const t = useTranslations("agents");
  const [filters, setFilters] = useState<FleetFiltersState>({
    status: "all",
    search: "",
  });

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <FleetFilters filters={filters} onFiltersChange={setFilters} />
      <FleetOverview filters={filters} />
    </div>
  );
}
