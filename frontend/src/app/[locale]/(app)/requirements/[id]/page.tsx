"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { PriorityBadge } from "@/components/shared/priority-badge";
import { RequirementHeader } from "@/components/requirements/requirement-header";
import { RequirementInfo } from "@/components/requirements/requirement-info";
import { ChangeHistory } from "@/components/requirements/change-history";
import { SimilarRequirements } from "@/components/requirements/similar-requirements";
import { ContextMessages } from "@/components/requirements/context-messages";
import { ConfirmDialog } from "@/components/requirements/confirm-dialog";
import { RejectSheet } from "@/components/requirements/reject-sheet";
import { useRequirement } from "@/lib/hooks/use-requirements";

export default function RequirementDetailPage() {
  const t = useTranslations("requirements");
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { data: requirement, isLoading, mutate } = useRequirement(id);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-8 w-96" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 space-y-4">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </div>
    );
  }

  if (!requirement) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <p>{t("notFound")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <RequirementHeader
        requirement={requirement}
        onConfirm={() => setConfirmId(id)}
        onReject={() => setRejectId(id)}
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left column - 2/3 */}
        <div className="md:col-span-2 space-y-6">
          <RequirementInfo requirement={requirement} />
          <ChangeHistory history={requirement.history} />
          <ContextMessages requirementId={id} />
        </div>

        {/* Right column - 1/3 metadata sidebar */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{t("detail")}</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">{t("status")}</dt>
                  <dd>
                    <StatusBadge status={requirement.status} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">{t("priority")}</dt>
                  <dd>
                    <PriorityBadge priority={requirement.priority} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">{t("category")}</dt>
                  <dd>
                    <Badge variant="secondary">{requirement.category}</Badge>
                  </dd>
                </div>
                <div className="border-t pt-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">{t("createdAt")}</dt>
                    <dd>
                      {new Date(requirement.created_at).toLocaleDateString()}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">{t("updatedAt")}</dt>
                    <dd>
                      {new Date(requirement.updated_at).toLocaleDateString()}
                    </dd>
                  </div>
                </div>
                {requirement.confirmed_by && (
                  <div className="border-t pt-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <dt className="text-muted-foreground">
                        {t("confirmedBy")}
                      </dt>
                      <dd>{requirement.confirmed_by}</dd>
                    </div>
                    {requirement.confirmed_at && (
                      <div className="flex items-center justify-between">
                        <dt className="text-muted-foreground">
                          {t("confirmedAt")}
                        </dt>
                        <dd>
                          {new Date(
                            requirement.confirmed_at,
                          ).toLocaleDateString()}
                        </dd>
                      </div>
                    )}
                  </div>
                )}
                {requirement.rejection_reason && (
                  <div className="border-t pt-3">
                    <dt className="text-muted-foreground mb-1">
                      {t("rejectionReason")}
                    </dt>
                    <dd className="rounded-md bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                      {requirement.rejection_reason}
                    </dd>
                  </div>
                )}
              </dl>
            </CardContent>
          </Card>

          <SimilarRequirements requirementId={id} />
        </div>
      </div>

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
