"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { CostChart } from "@/components/analytics/cost-chart";
import { TokenBreakdown } from "@/components/analytics/token-breakdown";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DollarSign, Coins, TrendingDown } from "lucide-react";

type Period = "7d" | "30d" | "90d";

export default function CostUsagePage() {
  const [period, setPeriod] = useState<Period>("30d");

  // Mock summary data
  const summary = {
    totalCost: 1247.83,
    totalTokens: 15_420_000,
    avgDailyCost: 41.59,
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Cost & Usage" />
        <div className="flex gap-1 rounded-lg border p-1 shrink-0">
          {(["7d", "30d", "90d"] as Period[]).map((p) => (
            <Button
              key={p}
              variant={period === p ? "default" : "ghost"}
              size="sm"
              onClick={() => setPeriod(p)}
            >
              {p}
            </Button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-0">
            <div className="flex items-center gap-3">
              <DollarSign className="h-5 w-5 text-green-600" />
              <div>
                <p className="text-2xl font-bold">${summary.totalCost.toLocaleString()}</p>
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
                <p className="text-2xl font-bold">{(summary.totalTokens / 1_000_000).toFixed(1)}M</p>
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
                <p className="text-2xl font-bold">${summary.avgDailyCost.toFixed(2)}</p>
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
