"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import useSWR from "swr";

import { ApprovalFilters } from "./approval-filters";
import { ApprovalList } from "./approval-list";
import { PageHeader } from "@/shared/ui/page-header";
import {
  approveControlPlaneApproval,
  listControlPlaneApprovals,
  rejectControlPlaneApproval,
  type ControlPlaneApproval,
} from "@/entities/control-plane";
import type { ApprovalRequest } from "@/lib/api/types";

function approvalUrgency(
  approval: ControlPlaneApproval,
): ApprovalRequest["urgency"] {
  const urgency = approval.metadata.urgency;
  if (urgency === "urgent" || urgency === "normal" || urgency === "low") {
    return urgency;
  }
  return "normal";
}

function toApprovalRequest(approval: ControlPlaneApproval): ApprovalRequest {
  return {
    id: approval.approval_id,
    source_agent_id: approval.source_agent_id,
    approval_type: approval.category,
    title: approval.proposed_action,
    summary: approval.reason || approval.risk,
    context_link: approval.artifact_links[0],
    urgency: approvalUrgency(approval),
    status: "pending",
    created_at: approval.created_at,
    resolved_at: approval.resolved_at ?? undefined,
    resolved_by: approval.resolved_by ?? undefined,
  };
}

export function ApprovalsPageWidget() {
  const t = useTranslations("approvals");
  const tc = useTranslations("common");
  const [activeType, setActiveType] = useState<string | undefined>(undefined);
  const { data, error, isLoading, mutate } = useSWR(
    ["control-plane-approvals", "pending"],
    () => listControlPlaneApprovals({ status: "pending", limit: 200 }),
    { refreshInterval: 15000 },
  );
  const approvals = useMemo(
    () => (data?.approvals ?? []).map(toApprovalRequest),
    [data?.approvals],
  );

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
    async (id: string) => {
      try {
        await approveControlPlaneApproval(id, { resolved_by: "human:operator" });
        await mutate();
        toast.success(t("approved"));
      } catch (err) {
        console.error("[approvals] approve failed", err);
        toast.error(tc("error"));
      }
    },
    [mutate, t, tc],
  );

  const handleReject = useCallback(
    async (id: string) => {
      try {
        await rejectControlPlaneApproval(id, { resolved_by: "human:operator" });
        await mutate();
        toast.success(t("rejected"));
      } catch (err) {
        console.error("[approvals] reject failed", err);
        toast.error(tc("error"));
      }
    },
    [mutate, t, tc],
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("title")} description={t("description")} />
      <ApprovalFilters
        activeType={activeType}
        onTypeChange={setActiveType}
        counts={counts}
      />
      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          {tc("loading")}
        </div>
      ) : error ? (
        <div className="flex items-center justify-center py-16 text-destructive">
          {tc("error")}
        </div>
      ) : (
        <ApprovalList
          approvals={filtered}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}
    </div>
  );
}
