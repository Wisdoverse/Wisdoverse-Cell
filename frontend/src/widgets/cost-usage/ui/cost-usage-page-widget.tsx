"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Coins, DollarSign, TrendingDown } from "lucide-react";

import { CostChart } from "./cost-chart";
import { TokenBreakdown } from "./token-breakdown";
import { PageHeader } from "@/shared/ui/page-header";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import {
  COST_USAGE_PERIODS,
  costUsagePeriodDays,
  type CostUsagePeriod,
} from "@/entities/usage/model/cost-usage";
import { getLLMUsage } from "@/lib/api/admin";
import type { LLMUsageResponse } from "@/lib/api/types";

function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function datesForPeriod(period: CostUsagePeriod): string[] {
  const days = costUsagePeriodDays(period);
  const today = new Date();
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(today);
    date.setUTCDate(today.getUTCDate() - (days - index - 1));
    return formatDate(date);
  });
}

function summarizeUsage(rows: LLMUsageResponse[]) {
  const totalInputTokens = rows.reduce(
    (total, row) => total + row.total_input_tokens,
    0,
  );
  const totalOutputTokens = rows.reduce(
    (total, row) => total + row.total_output_tokens,
    0,
  );
  const totalCost = rows.reduce((total, row) => total + row.total_cost_usd, 0);
  return {
    totalCost,
    totalTokens: totalInputTokens + totalOutputTokens,
    avgDailyCost: rows.length > 0 ? totalCost / rows.length : 0,
  };
}

function hasUsageData(rows: LLMUsageResponse[]): boolean {
  return rows.some(
    (row) =>
      row.total_calls > 0 ||
      row.total_cost_usd > 0 ||
      row.total_input_tokens > 0 ||
      row.total_output_tokens > 0,
  );
}

export function CostUsagePageWidget() {
  const t = useTranslations("costUsage");
  const tc = useTranslations("common");
  const [period, setPeriod] = useState<CostUsagePeriod>("30d");
  const dates = useMemo(() => datesForPeriod(period), [period]);
  const { data, error, isLoading } = useSWR(["llm-usage-period", dates], () =>
    Promise.all(dates.map((date) => getLLMUsage(date))),
  );
  const usageRows = data ?? [];
  const summary = summarizeUsage(usageRows);
  const hasData = hasUsageData(usageRows);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title={t("title")} />
        <div className="flex shrink-0 gap-1 rounded-lg border p-1">
          {COST_USAGE_PERIODS.map((nextPeriod) => (
            <Button
              key={nextPeriod}
              variant={period === nextPeriod ? "default" : "ghost"}
              size="sm"
              onClick={() => setPeriod(nextPeriod)}
            >
              {nextPeriod}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {tc("error")}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="pt-0">
            <div className="flex items-center gap-3">
              <DollarSign className="h-5 w-5 text-green-600" />
              <div>
                <p className="text-2xl font-bold">
                  {isLoading || !hasData ? "--" : `$${summary.totalCost.toFixed(2)}`}
                </p>
                <p className="text-xs text-muted-foreground">{t("totalCost")}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-0">
            <div className="flex items-center gap-3">
              <Coins className="h-5 w-5 text-blue-600" />
              <div>
                <p className="text-2xl font-bold">
                  {isLoading || !hasData
                    ? "--"
                    : (summary.totalTokens / 1_000_000).toFixed(1) + "M"}
                </p>
                <p className="text-xs text-muted-foreground">{t("totalTokens")}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-0">
            <div className="flex items-center gap-3">
              <TrendingDown className="h-5 w-5 text-amber-600" />
              <div>
                <p className="text-2xl font-bold">
                  {isLoading || !hasData ? "--" : `$${summary.avgDailyCost.toFixed(2)}`}
                </p>
                <p className="text-xs text-muted-foreground">{t("avgDailyCost")}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <CostChart data={usageRows} isLoading={isLoading} />
      <TokenBreakdown data={usageRows} isLoading={isLoading} />
    </div>
  );
}
