"use client";

import { useState } from "react";
import { useRequirements } from "@/entities/requirement/model/use-requirements";
import { RequirementsTable } from "@/entities/requirement";
import { confirmRequirement, rejectRequirement } from "@/lib/api/feedback";
import { toast } from "sonner";

export default function RmRequirementsWidget() {
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const pageSize = 10;

  const { data, isLoading, mutate } = useRequirements({
    page,
    page_size: pageSize,
  });

  const handleConfirm = async (id: string) => {
    try {
      await confirmRequirement(id, "human-user");
      toast.success("Requirement confirmed");
      mutate();
    } catch {
      toast.error("Failed to confirm");
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectRequirement(id, "Rejected via agent detail");
      toast.success("Requirement rejected");
      mutate();
    } catch {
      toast.error("Failed to reject");
    }
  };

  return (
    <RequirementsTable
      data={data?.items ?? []}
      isLoading={isLoading}
      page={page}
      pageSize={pageSize}
      total={data?.total ?? 0}
      onPageChange={setPage}
      selectedIds={selectedIds}
      onSelectionChange={setSelectedIds}
      onConfirm={handleConfirm}
      onReject={handleReject}
    />
  );
}
