"use client";

import { useTranslations } from "next-intl";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";
import type { HealthReadyResponse } from "@/lib/api/types";

interface HealthGridProps {
  data: HealthReadyResponse | undefined;
  isLoading: boolean;
}

const SERVICE_KEYS = ["postgres", "redis", "milvus", "nats"] as const;

function StatusDot({ status }: { status: string }) {
  const color =
    status === "ok" || status === "healthy"
      ? "bg-green-500"
      : "bg-red-500";

  return (
    <span
      className={`inline-block h-3 w-3 rounded-full ${color}`}
      aria-label={status}
    />
  );
}

export function HealthGrid({ data, isLoading }: HealthGridProps) {
  const t = useTranslations("monitor");

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("systemHealth")}</CardTitle>
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

  const checks = data?.checks || {};
  const allHealthy = Object.values(checks).every(
    (c) => c.status === "ok" || c.status === "healthy",
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("systemHealth")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {SERVICE_KEYS.map((key) => {
            const check = checks[key];
            return (
              <div
                key={key}
                className="flex flex-col items-center gap-2 rounded-lg border p-4"
              >
                <StatusDot status={check?.status || "unknown"} />
                <span className="text-sm font-medium">
                  {t(`services.${key}`)}
                </span>
                {check?.latency_ms !== undefined && (
                  <span className="text-xs text-muted-foreground">
                    {check.latency_ms.toFixed(0)}ms
                  </span>
                )}
              </div>
            );
          })}
        </div>
        <p
          className={`text-sm font-medium ${allHealthy ? "text-green-600" : "text-red-600"}`}
        >
          {allHealthy ? t("allServicesNormal") : t("serviceDown")}
        </p>
      </CardContent>
    </Card>
  );
}
