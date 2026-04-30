"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { resetCircuitBreaker } from "@/lib/api/admin";
import type { CircuitBreakerResponse } from "@/lib/api/types";

interface CircuitBreakerCardProps {
  data: CircuitBreakerResponse | undefined;
  isLoading: boolean;
}

function getStateColor(state: string): string {
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

function getStateLabel(
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

export function CircuitBreakerCard({
  data,
  isLoading,
}: CircuitBreakerCardProps) {
  const t = useTranslations("dashboard");
  const tMonitor = useTranslations("monitor");
  const { mutate } = useSWRConfig();
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    setResetting(true);
    try {
      await resetCircuitBreaker();
      await mutate("circuit-breaker");
      toast.success(tMonitor("resetSuccess"));
    } catch (err) {
      console.error("[circuit-breaker] Reset failed:", err);
      toast.error(tMonitor("resetFailed"));
    } finally {
      setResetting(false);
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("circuitBreaker")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  const state = data?.state || "unknown";

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("circuitBreaker")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <span
            className={`inline-block h-4 w-4 rounded-full ${getStateColor(state)}`}
          />
          <span className="text-lg font-semibold">
            {getStateLabel(state, t)}
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleReset}
          disabled={resetting}
        >
          {tMonitor("resetCircuitBreaker")}
        </Button>
      </CardContent>
    </Card>
  );
}
