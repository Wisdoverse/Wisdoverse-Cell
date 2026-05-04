"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { RequirementsFilters } from "./requirements-filters";
import { RequirementsTable } from "@/entities/requirement";
import {
  BatchActions,
  ConfirmDialog,
  RejectSheet,
} from "@/features/requirement-review";
import { PageHeader } from "@/shared/ui/page-header";
import { useRequirements } from "@/entities/requirement/model/use-requirements";
import type { RequirementFilters } from "@/lib/api/types";

export function RequirementsPageWidget() {
  const t = useTranslations("requirements");
  const [filters, setFilters] = useState<RequirementFilters>({
    page: 1,
    page_size: 20,
  });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const { data, isLoading, mutate } = useRequirements(filters);

  return (
    <div className="space-y-4">
      <PageHeader title={t("title")} />
      <RequirementsFilters filters={filters} onFiltersChange={setFilters} />
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
        data={data?.items || []}
        isLoading={isLoading}
        page={filters.page || 1}
        pageSize={filters.page_size || 20}
        total={data?.total || 0}
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
