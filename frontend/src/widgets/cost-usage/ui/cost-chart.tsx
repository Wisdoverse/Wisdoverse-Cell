"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import type { LLMUsageResponse } from "@/lib/api/types";

interface CostChartProps {
  data: LLMUsageResponse[];
  isLoading: boolean;
}

export function CostChart({ data, isLoading }: CostChartProps) {
  const t = useTranslations("costUsage");
  const chartData = data.map((row) => ({
    date: row.date ?? "",
    cost: row.total_cost_usd,
  }));
  const maxCost = Math.max(0, ...chartData.map((d) => d.cost));

  // Show last 14 bars max for readability
  const visibleData = chartData.slice(-14);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("dailyCost")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="bg-muted h-48 animate-pulse rounded-lg" />
        ) : maxCost <= 0 ? (
          <div className="text-muted-foreground flex h-48 items-center justify-center text-sm">
            {t("noCostData")}
          </div>
        ) : (
          <div className="flex h-48 min-w-0 items-end gap-1">
            {visibleData.map((d, i) => (
              <div key={i} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <span className="text-muted-foreground text-[10px]">${d.cost.toFixed(0)}</span>
                <div
                  className="min-h-[2px] w-full rounded-t bg-indigo-500/80 transition-colors hover:bg-indigo-500"
                  style={{
                    height: `${maxCost > 0 ? (d.cost / maxCost) * 100 : 0}%`,
                  }}
                />
                <span className="text-muted-foreground w-full truncate text-center text-[9px]">
                  {d.date.slice(5)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
