"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { History } from "lucide-react";
import type { HistoryEntry } from "@/lib/api/types";

interface ChangeHistoryProps {
  history: HistoryEntry[];
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

function formatChanges(changes: Record<string, unknown>): string[] {
  return Object.entries(changes).map(([key, value]) => {
    if (
      typeof value === "object" &&
      value !== null &&
      "old" in value &&
      "new" in value
    ) {
      const v = value as { old: unknown; new: unknown };
      return `${key}: ${String(v.old)} → ${String(v.new)}`;
    }
    return `${key}: ${String(value)}`;
  });
}

export function ChangeHistory({ history }: ChangeHistoryProps) {
  const t = useTranslations("requirements");

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
          <p className="text-sm text-muted-foreground">{t("noHistory")}</p>
        ) : (
          <div className="relative ml-3 border-l-2 border-muted pl-6 space-y-6">
            {history.map((entry, index) => (
              <div key={index} className="relative">
                <div className="absolute -left-[31px] top-1 h-3 w-3 rounded-full border-2 border-background bg-muted-foreground" />
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{entry.action}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatRelativeTime(entry.timestamp)}
                    </span>
                  </div>
                  {entry.by && (
                    <p className="text-xs text-muted-foreground">
                      by {entry.by}
                    </p>
                  )}
                  {Object.keys(entry.changes).length > 0 && (
                    <ul className="text-xs text-muted-foreground space-y-0.5">
                      {formatChanges(entry.changes).map((change, i) => (
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
