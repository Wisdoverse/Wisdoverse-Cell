"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, X } from "lucide-react";
import { Button } from "@/shared/ui/button";
import type { Requirement } from "@/lib/api/types";

interface RequirementHeaderProps {
  requirement: Requirement;
  onConfirm: () => void;
  onReject: () => void;
}

export function RequirementHeader({ requirement, onConfirm, onReject }: RequirementHeaderProps) {
  const t = useTranslations("requirements");
  const tc = useTranslations("common");
  const router = useRouter();

  return (
    <div className="space-y-3">
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground gap-1"
        onClick={() => router.push("../requirements")}
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToList")}
      </Button>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight break-words">{requirement.title}</h1>
        {requirement.status === "pending" && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="border-green-200 text-green-600 hover:bg-green-50"
              onClick={onConfirm}
            >
              <Check className="mr-1 h-4 w-4" />
              {tc("confirm")}
            </Button>
            <Button
              variant="outline"
              className="border-red-200 text-red-600 hover:bg-red-50"
              onClick={onReject}
            >
              <X className="mr-1 h-4 w-4" />
              {tc("reject")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
