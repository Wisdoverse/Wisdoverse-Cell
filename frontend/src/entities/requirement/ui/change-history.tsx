"use client";

import { useLocale, useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { History } from "lucide-react";
import type { HistoryEntry } from "@/lib/api/types";

interface ChangeHistoryProps {
  history: HistoryEntry[];
}

type TranslationFn = (key: string, values?: Record<string, string | number>) => string;

function formatRelativeTime(dateStr: string, locale: string, justNow: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  if (diffMin < 1) return justNow;
  if (diffMin < 60) return formatter.format(-diffMin, "minute");
  if (diffHr < 24) return formatter.format(-diffHr, "hour");
  if (diffDay < 7) return formatter.format(-diffDay, "day");
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date);
}

function formatChangeField(key: string, t: TranslationFn): string {
  const fieldLabels: Record<string, string> = {
    status: t("status"),
    priority: t("priority"),
    category: t("category"),
    title: t("titleField"),
    description: t("description"),
    rejection_reason: t("rejectionReason"),
    confirmed_by: t("confirmedBy"),
  };
  return fieldLabels[key] ?? key.replace(/_/g, " ");
}

function formatChangeValue(key: string, value: unknown, t: TranslationFn): string {
  if (typeof value !== "string") return String(value);
  if (key === "status") {
    const labels: Record<string, string> = {
      pending: t("statusPending"),
      confirmed: t("statusConfirmed"),
      rejected: t("statusRejected"),
      changed: t("statusChanged"),
    };
    return labels[value] ?? value;
  }
  if (key === "priority") {
    const labels: Record<string, string> = {
      high: t("priorityHigh"),
      medium: t("priorityMedium"),
      low: t("priorityLow"),
    };
    return labels[value] ?? value;
  }
  return value;
}

function formatChanges(changes: Record<string, unknown>, t: TranslationFn): string[] {
  return Object.entries(changes).map(([key, value]) => {
    const field = formatChangeField(key, t);
    if (typeof value === "object" && value !== null && "old" in value && "new" in value) {
      const v = value as { old: unknown; new: unknown };
      return t("changeFromTo", {
        field,
        oldValue: formatChangeValue(key, v.old, t),
        newValue: formatChangeValue(key, v.new, t),
      });
    }
    return t("changeValue", {
      field,
      value: formatChangeValue(key, value, t),
    });
  });
}

export function ChangeHistory({ history }: ChangeHistoryProps) {
  const t = useTranslations("requirements");
  const locale = useLocale();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="h-4 w-4" />
          {t("changeHistory")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noHistory")}</p>
        ) : (
          <div className="border-muted relative ml-3 space-y-6 border-l-2 pl-6">
            {history.map((entry, index) => (
              <div key={index} className="relative">
                <div className="border-background bg-muted-foreground absolute top-1 -left-[31px] h-3 w-3 rounded-full border-2" />
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{entry.action}</span>
                    <span className="text-muted-foreground text-xs">
                      {formatRelativeTime(entry.timestamp, locale, t("justNow"))}
                    </span>
                  </div>
                  {entry.by && (
                    <p className="text-muted-foreground text-xs">
                      {t("changedBy", { actor: entry.by })}
                    </p>
                  )}
                  {Object.keys(entry.changes).length > 0 && (
                    <ul className="text-muted-foreground space-y-0.5 text-xs">
                      {formatChanges(entry.changes, t).map((change, i) => (
                        <li key={i}>{change}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
