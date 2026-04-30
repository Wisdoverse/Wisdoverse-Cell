"use client";

import { Badge } from "@/components/ui/badge";
import { useTranslations } from "next-intl";
import type { Priority } from "@/lib/api/types";

const priorityVariants: Record<Priority, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  medium:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  const t = useTranslations("requirements");
  const labelMap: Record<Priority, string> = {
    high: t("priorityHigh"),
    medium: t("priorityMedium"),
    low: t("priorityLow"),
  };

  return (
    <Badge variant="outline" className={priorityVariants[priority]}>
      {labelMap[priority]}
    </Badge>
  );
}
