"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface CostChartProps {
  period: string;
}

function seedRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function generateCostData(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    date: new Date(Date.now() - (count - i) * 86400000).toLocaleDateString("en", { month: "short", day: "numeric" }),
    cost: Math.round((20 + seedRandom(i + 42) * 60) * 100) / 100,
  }));
}

export function CostChart({ period }: CostChartProps) {
  const count = period === "7d" ? 7 : period === "30d" ? 30 : 90;
  const [data] = useState(() => generateCostData(count));
  const maxCost = Math.max(...data.map((d) => d.cost));

  // Show last 14 bars max for readability
  const visibleData = data.slice(-14);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Daily Cost</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-1 h-48">
          {visibleData.map((d, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-[10px] text-muted-foreground">
                ${d.cost.toFixed(0)}
              </span>
              <div
                className="w-full rounded-t bg-indigo-500/80 hover:bg-indigo-500 transition-colors min-h-[2px]"
                style={{ height: `${(d.cost / maxCost) * 100}%` }}
              />
              <span className="text-[9px] text-muted-foreground truncate w-full text-center">
                {d.date}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
