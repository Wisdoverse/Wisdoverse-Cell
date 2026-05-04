"use client";

import { useTranslations } from "next-intl";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";
import type { LLMUsageResponse } from "@/lib/api/types";

interface LLMStatsPanelProps {
  data: LLMUsageResponse | undefined;
  isLoading: boolean;
}

function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}K`;
  }
  return String(count);
}

export function LLMStatsPanel({ data, isLoading }: LLMStatsPanelProps) {
  const t = useTranslations("dashboard");

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("llmUsage")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const totalTokens =
    (data?.total_input_tokens || 0) + (data?.total_output_tokens || 0);

  const stats = [
    {
      label: t("cost"),
      value: `$${(data?.total_cost_usd || 0).toFixed(2)}`,
    },
    {
      label: t("tokens"),
      value: formatTokens(totalTokens),
    },
    {
      label: t("calls"),
      value: String(data?.total_calls || 0),
    },
    {
      label: t("avgLatency"),
      value: `${(data?.avg_latency_ms || 0).toFixed(0)}ms`,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("llmUsage")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-lg border p-4">
              <p className="text-sm text-muted-foreground">{stat.label}</p>
              <p className="text-2xl font-bold mt-1">{stat.value}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
