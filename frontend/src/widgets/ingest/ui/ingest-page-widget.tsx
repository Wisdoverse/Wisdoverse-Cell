"use client";

import { useState } from "react";
import { CheckCircle2, CircleHelp, ClipboardList } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { IngestResult, UploadForm } from "@/features/content-ingest";
import { PageHeader } from "@/shared/ui/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import type { IngestResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const guidanceIcons: Record<string, LucideIcon> = {
  extract: ClipboardList,
  questions: CircleHelp,
  review: CheckCircle2,
};

function guidanceToneClass(index: number): string {
  return [
    "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-200",
    "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-200",
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200",
  ][index] ?? "bg-slate-100 text-slate-700 dark:bg-slate-900/50 dark:text-slate-200";
}

function IngestGuidance() {
  const t = useTranslations("ingest");
  const steps = ["extract", "questions", "review"];

  return (
    <section
      aria-label={t("guidanceAriaLabel")}
      className="grid grid-cols-1 gap-3 md:grid-cols-3"
    >
      {steps.map((step, index) => {
        const Icon = guidanceIcons[step];
        return (
          <div key={step} className="rounded-lg border bg-card p-4">
            <div className="flex gap-3">
              <div
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-lg",
                  guidanceToneClass(index),
                )}
              >
                <Icon className="size-5" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {t(`guidance.${step}.title`)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t(`guidance.${step}.description`)}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export function IngestPageWidget() {
  const t = useTranslations("ingest");
  const [result, setResult] = useState<IngestResponse | null>(null);

  if (result) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("title")} description={t("description")} />
        <IngestResult result={result} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <IngestGuidance />
      <Tabs defaultValue="upload">
        <TabsList>
          <TabsTrigger value="upload">{t("uploadTab")}</TabsTrigger>
          <TabsTrigger value="wechat">{t("wechatTab")}</TabsTrigger>
        </TabsList>
        <TabsContent value="upload" className="mt-4">
          <UploadForm source="manual" onSuccess={setResult} />
        </TabsContent>
        <TabsContent value="wechat" className="mt-4">
          <UploadForm source="wechat" onSuccess={setResult} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
