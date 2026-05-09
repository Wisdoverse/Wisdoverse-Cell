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
          <div className="h-48 animate-pulse rounded-lg bg-muted" />
        ) : maxCost <= 0 ? (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            {t("noCostData")}
          </div>
        ) : (
        <div className="flex items-end gap-1 h-48">
          {visibleData.map((d, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-[10px] text-muted-foreground">
                ${d.cost.toFixed(0)}
              </span>
              <div
                className="w-full rounded-t bg-indigo-500/80 hover:bg-indigo-500 transition-colors min-h-[2px]"
                style={{ height: `${maxCost > 0 ? (d.cost / maxCost) * 100 : 0}%` }}
              />
              <span className="text-[9px] text-muted-foreground truncate w-full text-center">
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
