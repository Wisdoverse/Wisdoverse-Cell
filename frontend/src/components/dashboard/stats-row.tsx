"use client";

import { useTranslations } from "next-intl";
import { StatCard } from "@/components/shared/stat-card";

interface StatsRowProps {
  counts: Record<string, number>;
  isLoading: boolean;
}

export function StatsRow({ counts, isLoading }: StatsRowProps) {
  const t = useTranslations("dashboard");
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard
        label={t("pending")}
        value={counts.pending || 0}
        className="text-yellow-600"
      />
      <StatCard
        label={t("confirmed")}
        value={counts.confirmed || 0}
        className="text-green-600"
      />
      <StatCard
        label={t("rejected")}
        value={counts.rejected || 0}
        className="text-red-600"
      />
      <StatCard
        label={t("total")}
        value={total}
        className="text-blue-600"
      />
    </div>
  );
}
