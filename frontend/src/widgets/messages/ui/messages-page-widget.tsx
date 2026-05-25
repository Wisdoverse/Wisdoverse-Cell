"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, MessageSquareText, Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { MessageSearch } from "./message-search";
import { MessageTable } from "./message-table";
import { PageHeader } from "@/shared/ui/page-header";
import { searchMessages } from "@/lib/api/messages";
import type { MessageSearchParams, MessageSearchResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type MessageSummaryKey = "shown" | "extracted" | "sessions";

interface MessageSummaryMetric {
  key: MessageSummaryKey;
  value: number;
  icon: LucideIcon;
  tone: "slate" | "emerald" | "sky";
}

function summaryToneClass(tone: MessageSummaryMetric["tone"]): string {
  return {
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-900/50 dark:text-slate-200",
    emerald:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200",
    sky: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-200",
  }[tone];
}

function summarizeMessages(results: MessageSearchResult[]): MessageSummaryMetric[] {
  const sessionCount = new Set(
    results.map((result) => result.session_id).filter(Boolean),
  ).size;

  return [
    { key: "shown", value: results.length, icon: Search, tone: "slate" },
    {
      key: "extracted",
      value: results.filter((result) => result.extracted).length,
      icon: CheckCircle2,
      tone: "emerald",
    },
    {
      key: "sessions",
      value: sessionCount,
      icon: MessageSquareText,
      tone: "sky",
    },
  ];
}

function MessageSearchSummary({ results }: { results: MessageSearchResult[] }) {
  const t = useTranslations("messages");
  const metrics = useMemo(() => summarizeMessages(results), [results]);

  return (
    <section
      aria-label={t("summaryAriaLabel")}
      className="grid grid-cols-1 gap-3 md:grid-cols-3"
    >
      {metrics.map((metric) => {
        const Icon = metric.icon;
        return (
          <div key={metric.key} className="rounded-lg border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-3xl font-semibold leading-none tracking-normal tabular-nums">
                  {metric.value}
                </div>
                <p className="mt-2 text-sm font-medium">
                  {t(`summary.${metric.key}.label`)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t(`summary.${metric.key}.description`)}
                </p>
              </div>
              <div
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-lg",
                  summaryToneClass(metric.tone),
                )}
              >
                <Icon className="size-5" />
              </div>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export function MessagesPageWidget() {
  const t = useTranslations("messages");
  const tc = useTranslations("common");
  const [params, setParams] = useState<MessageSearchParams>({});
  const [results, setResults] = useState<MessageSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch() {
    setIsLoading(true);
    setHasSearched(true);
    try {
      const data = await searchMessages(params);
      setResults(data);
    } catch (err) {
      console.error("[messages] Search failed:", err);
      toast.error(tc("error"));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <MessageSearch
        params={params}
        onChange={setParams}
        onSearch={handleSearch}
        isLoading={isLoading}
      />
      {hasSearched && !isLoading ? <MessageSearchSummary results={results} /> : null}
      {hasSearched && <MessageTable data={results} isLoading={isLoading} />}
    </div>
  );
}
