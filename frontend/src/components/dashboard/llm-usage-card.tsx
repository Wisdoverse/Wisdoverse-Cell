"use client";

import { useTranslations } from "next-intl";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/shared/ui/card";
import type {
  LLMUsageResponse,
  CircuitBreakerResponse,
} from "@/lib/api/types";

interface LLMUsageCardProps {
  data: LLMUsageResponse | undefined;
  circuitBreaker: CircuitBreakerResponse | undefined;
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

function getCircuitBreakerColor(state: string): string {
  switch (state.toLowerCase()) {
    case "closed":
      return "bg-green-500";
    case "open":
      return "bg-red-500";
    case "half-open":
    case "half_open":
      return "bg-yellow-500";
    default:
      return "bg-gray-400";
  }
}

function getCircuitBreakerLabel(
  state: string,
  t: ReturnType<typeof useTranslations<"dashboard">>,
): string {
  switch (state.toLowerCase()) {
    case "closed":
      return t("circuitClosed");
    case "open":
      return t("circuitOpen");
    case "half-open":
    case "half_open":
      return t("circuitHalfOpen");
    default:
      return state;
  }
}

export function LLMUsageCard({
  data,
  circuitBreaker,
  isLoading,
}: LLMUsageCardProps) {
  const t = useTranslations("dashboard");

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("llmUsage")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const totalTokens =
    (data?.total_input_tokens || 0) + (data?.total_output_tokens || 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("llmUsage")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border p-3">
            <p className="text-sm text-muted-foreground">{t("cost")}</p>
            <p className="text-2xl font-bold">
              ${(data?.total_cost_usd || 0).toFixed(2)}
            </p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-sm text-muted-foreground">{t("tokens")}</p>
            <p className="text-2xl font-bold">{formatTokens(totalTokens)}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-sm text-muted-foreground">{t("calls")}</p>
            <p className="text-2xl font-bold">{data?.total_calls || 0}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-sm text-muted-foreground">{t("avgLatency")}</p>
            <p className="text-2xl font-bold">
              {(data?.avg_latency_ms || 0).toFixed(0)}ms
            </p>
          </div>
        </div>

        {circuitBreaker && (
          <div className="flex items-center gap-2 rounded-lg border p-3">
            <span
              className={`inline-block h-3 w-3 rounded-full ${getCircuitBreakerColor(circuitBreaker.state)}`}
            />
            <span className="text-sm text-muted-foreground">
              {t("circuitBreaker")}:
            </span>
            <span className="text-sm font-medium">
              {getCircuitBreakerLabel(circuitBreaker.state, t)}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
