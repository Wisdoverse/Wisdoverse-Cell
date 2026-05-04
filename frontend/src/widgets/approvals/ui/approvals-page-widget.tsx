"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { ApprovalFilters } from "@/components/approvals/approval-filters";
import { ApprovalList } from "@/components/approvals/approval-list";
import { PageHeader } from "@/shared/ui/page-header";
import { MOCK_APPROVALS } from "@/entities/approval/model/mock-approvals";
import type { ApprovalRequest } from "@/lib/api/types";

export function ApprovalsPageWidget() {
  const t = useTranslations("approvals");
  const [activeType, setActiveType] = useState<string | undefined>(undefined);
  const [approvals, setApprovals] =
    useState<ApprovalRequest[]>(MOCK_APPROVALS);

  const filtered = useMemo(
    () =>
      activeType
        ? approvals.filter((approval) => approval.approval_type === activeType)
        : approvals,
    [activeType, approvals],
  );

  const counts = useMemo(() => {
    const nextCounts: Record<string, number> = { all: approvals.length };
    for (const approval of approvals) {
      nextCounts[approval.approval_type] =
        (nextCounts[approval.approval_type] ?? 0) + 1;
    }
    return nextCounts;
  }, [approvals]);

  const handleApprove = useCallback(
    (id: string) => {
      setApprovals((prev) => prev.filter((approval) => approval.id !== id));
      toast.success(t("approved"));
    },
    [t],
  );

  const handleReject = useCallback(
    (id: string) => {
      setApprovals((prev) => prev.filter((approval) => approval.id !== id));
      toast.success(t("rejected"));
    },
    [t],
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("title")} description={t("description")} />
      <ApprovalFilters
        activeType={activeType}
        onTypeChange={setActiveType}
        counts={counts}
      />
      <ApprovalList
        approvals={filtered}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}
