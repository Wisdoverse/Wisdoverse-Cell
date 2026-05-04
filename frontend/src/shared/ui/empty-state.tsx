"use client";

import { useTranslations } from "next-intl";

interface EmptyStateProps {
  message?: string;
  icon?: React.ReactNode;
}

export function EmptyState({ message, icon }: EmptyStateProps) {
  const t = useTranslations("common");
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
      {icon && <div className="mb-4">{icon}</div>}
      <p className="text-sm">{message || t("noData")}</p>
    </div>
  );
}
