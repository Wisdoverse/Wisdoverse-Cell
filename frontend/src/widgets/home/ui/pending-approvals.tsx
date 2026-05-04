"use client";

import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { ArrowRight, InboxIcon } from "lucide-react";
import { ApprovalCard } from "@/entities/approval/ui/approval-card";
import { useApprovals } from "@/entities/approval/model/use-approvals";

export function PendingApprovals() {
  const t = useTranslations("home");
  const locale = useLocale();
  const { data, isLoading } = useApprovals({ status: "pending" });

  const approvals = data?.approvals ?? [];
  const displayApprovals = approvals.slice(0, 3);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight">
          {t("pendingApprovals")}
          {!isLoading && approvals.length > 0 && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({approvals.length})
            </span>
          )}
        </h2>
        <Link
          href={`/${locale}/approvals`}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {t("viewAll")}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-32 bg-muted animate-pulse rounded-xl"
            />
          ))}
        </div>
      ) : displayApprovals.length > 0 ? (
        <div className="space-y-3">
          {displayApprovals.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} />
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-xl border bg-card py-8 text-center">
          <InboxIcon className="h-8 w-8 text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">{t("noApprovals")}</p>
        </div>
      )}
    </section>
  );
}
