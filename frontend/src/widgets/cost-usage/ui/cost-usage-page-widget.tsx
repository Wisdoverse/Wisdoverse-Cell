"use client";

import { useState } from "react";
import { Coins, DollarSign, TrendingDown } from "lucide-react";

import { CostChart } from "@/components/analytics/cost-chart";
import { TokenBreakdown } from "@/components/analytics/token-breakdown";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  COST_USAGE_PERIODS,
  MOCK_COST_SUMMARY,
  type CostUsagePeriod,
} from "@/entities/usage/model/mock-cost-summary";

export function CostUsagePageWidget() {
  const [period, setPeriod] = useState<CostUsagePeriod>("30d");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Cost & Usage" />
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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="pt-0">
            <div className="flex items-center gap-3">
              <DollarSign className="h-5 w-5 text-green-600" />
              <div>
                <p className="text-2xl font-bold">
                  ${MOCK_COST_SUMMARY.totalCost.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground">Total Cost</p>
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
                  {(MOCK_COST_SUMMARY.totalTokens / 1_000_000).toFixed(1)}M
                </p>
                <p className="text-xs text-muted-foreground">Total Tokens</p>
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
                  ${MOCK_COST_SUMMARY.avgDailyCost.toFixed(2)}
                </p>
                <p className="text-xs text-muted-foreground">Avg / Day</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <CostChart period={period} />
      <TokenBreakdown period={period} />
    </div>
  );
}
