"use client";

import { useTranslations } from "next-intl";
import type { ApprovalRequest } from "@/lib/api/types";
import { ApprovalCard } from "@/components/shared/approval-card";
import { cn } from "@/lib/utils";

interface ApprovalListProps {
  approvals: ApprovalRequest[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

const URGENCY_ORDER = ["urgent", "normal", "low"] as const;

export function ApprovalList({
  approvals,
  onApprove,
  onReject,
}: ApprovalListProps) {
  const t = useTranslations("approvals");

  if (approvals.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        {t("noApprovals")}
      </div>
    );
  }

  const grouped = URGENCY_ORDER.reduce(
    (acc, urgency) => {
      const items = approvals.filter((a) => a.urgency === urgency);
      if (items.length > 0) {
        acc[urgency] = items;
      }
      return acc;
    },
    {} as Record<string, ApprovalRequest[]>,
  );

  return (
    <div className="space-y-6">
      {URGENCY_ORDER.map((urgency) => {
        const items = grouped[urgency];
        if (!items) return null;

        return (
          <section key={urgency}>
            <h3
              className={cn(
                "text-sm font-semibold mb-3",
                urgency === "urgent" && "text-red-600 dark:text-red-400",
              )}
            >
              {t(urgency)}
            </h3>
            <div className="space-y-3">
              {items.map((approval) => (
                <ApprovalCard
                  key={approval.id}
                  approval={approval}
                  onApprove={() => onApprove(approval.id)}
                  onReject={() => onReject(approval.id)}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
