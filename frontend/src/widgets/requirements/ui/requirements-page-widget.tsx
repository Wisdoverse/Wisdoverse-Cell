"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { RequirementsFilters } from "./requirements-filters";
import { RequirementsTable } from "@/entities/requirement";
import {
  BatchActions,
  ConfirmDialog,
  RejectSheet,
} from "@/features/requirement-review";
import { PageHeader } from "@/shared/ui/page-header";
import { useRequirements } from "@/entities/requirement";
import type { RequirementFilters } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function SummaryTile({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: "amber" | "rose" | "emerald";
}) {
  const toneClass = {
    amber: "text-amber-600 dark:text-amber-300",
    rose: "text-rose-600 dark:text-rose-300",
    emerald: "text-emerald-600 dark:text-emerald-300",
  }[tone];

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold leading-none tabular-nums">{value}</div>
          <div className="text-muted-foreground mt-2 text-sm">{label}</div>
        </div>
        <Icon className={cn("size-5", toneClass)} />
      </div>
    </div>
  );
}

export function RequirementsPageWidget() {
  const t = useTranslations("requirements");
  const [filters, setFilters] = useState<RequirementFilters>({
    page: 1,
    page_size: 20,
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const { data, isLoading, mutate } = useRequirements(filters);
  const requirements = useMemo(() => data?.items ?? [], [data?.items]);
  const visibleRequirements = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return requirements;
    return requirements.filter((requirement) =>
      [
        requirement.title,
        requirement.description,
        requirement.source_quote ?? "",
        requirement.category,
      ]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query),
    );
  }, [requirements, searchQuery]);
  const pendingCount = useMemo(
    () => requirements.filter((requirement) => requirement.status === "pending").length,
    [requirements],
  );
  const highPriorityCount = useMemo(
    () => requirements.filter((requirement) => requirement.priority === "high").length,
    [requirements],
  );
  const openQuestionCount = useMemo(
    () =>
      requirements.reduce(
        (total, requirement) =>
          total +
          requirement.open_questions.filter((question) => question.status === "open").length,
        0,
      ),
    [requirements],
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("title")} description={t("pageDescription")} />
      <div className="grid gap-3 md:grid-cols-3">
        <SummaryTile
          label={t("pendingReviewSummary")}
          value={pendingCount}
          icon={CheckCircle2}
          tone="amber"
        />
        <SummaryTile
          label={t("highPrioritySummary")}
          value={highPriorityCount}
          icon={AlertTriangle}
          tone="rose"
        />
        <SummaryTile
          label={t("openQuestionsSummary")}
          value={openQuestionCount}
          icon={HelpCircle}
          tone="emerald"
        />
      </div>
      <RequirementsFilters
        filters={filters}
        onFiltersChange={setFilters}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
      />
      {selectedIds.length > 0 && (
        <BatchActions
          selectedIds={selectedIds}
          onComplete={() => {
            setSelectedIds([]);
            mutate();
          }}
        />
      )}
      <RequirementsTable
        data={visibleRequirements}
        isLoading={isLoading}
        page={filters.page || 1}
        pageSize={filters.page_size || 20}
        total={searchQuery.trim() ? visibleRequirements.length : data?.total || 0}
        onPageChange={(page) => setFilters((prev) => ({ ...prev, page }))}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        onConfirm={setConfirmId}
        onReject={setRejectId}
      />
      <ConfirmDialog
        id={confirmId}
        onClose={() => setConfirmId(null)}
        onSuccess={mutate}
      />
      <RejectSheet
        id={rejectId}
        onClose={() => setRejectId(null)}
        onSuccess={mutate}
      />
    </div>
  );
}
