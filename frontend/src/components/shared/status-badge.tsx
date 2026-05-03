"use client";

import { Badge } from "@/shared/ui/badge";
import { useTranslations } from "next-intl";
import type { RequirementStatus } from "@/lib/api/types";

const statusVariants: Record<RequirementStatus, string> = {
  pending:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  confirmed:
    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  rejected: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  changed: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
};

export function StatusBadge({ status }: { status: RequirementStatus }) {
  const t = useTranslations("requirements");
  const labelMap: Record<RequirementStatus, string> = {
    pending: t("statusPending"),
    confirmed: t("statusConfirmed"),
    rejected: t("statusRejected"),
    changed: t("statusChanged"),
  };

  return (
    <Badge variant="outline" className={statusVariants[status]}>
      {labelMap[status]}
    </Badge>
  );
}
