"use client";

import { useMemo } from "react";
import { CircleHelp, FileText, Timer } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { QuestionCard } from "@/features/question-answer";
import { PageHeader } from "@/shared/ui/page-header";
import { QueryBoundary } from "@/shared/ui/query-boundary";
import { useQuestions } from "@/entities/question";
import type { OpenQuestion } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type QuestionSummaryKey = "waiting" | "withContext" | "oldest";

interface QuestionSummaryMetric {
  key: QuestionSummaryKey;
  value: number | string;
  icon: LucideIcon;
  tone: "amber" | "sky" | "slate";
}

function daysSince(dateStr: string | undefined): number | null {
  if (!dateStr) return null;
  const timestamp = new Date(dateStr).getTime();
  if (Number.isNaN(timestamp)) return null;
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86400000));
}

function summarizeQuestions(questions: OpenQuestion[]): QuestionSummaryMetric[] {
  const withContext = questions.filter((question) => question.context).length;
  const oldestQuestion = questions
    .filter((question) => question.created_at)
    .sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    )[0];
  const oldestDays = daysSince(oldestQuestion?.created_at);

  return [
    { key: "waiting", value: questions.length, icon: CircleHelp, tone: "amber" },
    { key: "withContext", value: withContext, icon: FileText, tone: "sky" },
    {
      key: "oldest",
      value: oldestDays == null ? "-" : oldestDays,
      icon: Timer,
      tone: "slate",
    },
  ];
}

function summaryToneClass(tone: QuestionSummaryMetric["tone"]): string {
  return {
    amber:
      "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-200",
    sky: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-200",
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-900/50 dark:text-slate-200",
  }[tone];
}

function QuestionSummary({ questions }: { questions: OpenQuestion[] }) {
  const t = useTranslations("questions");
  const metrics = useMemo(() => summarizeQuestions(questions), [questions]);

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

export function QuestionsPageWidget() {
  const t = useTranslations("questions");
  const { data, error, isLoading, mutate } = useQuestions();

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <QueryBoundary
        data={data}
        error={error}
        isLoading={isLoading}
        isEmpty={(questions) => questions.length === 0}
        emptyMessage={t("noQuestions")}
        onRetry={() => mutate()}
      >
        {(questions) => (
          <div className="space-y-6">
            <QuestionSummary questions={questions} />
            <div className="space-y-4">
              {questions.map((question) => (
                <QuestionCard
                  key={question.id}
                  question={question}
                  onAnswered={() => mutate()}
                />
              ))}
            </div>
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
