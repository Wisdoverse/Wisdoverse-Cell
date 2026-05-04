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

export function RequirementHeader({
  requirement,
  onConfirm,
  onReject,
}: RequirementHeaderProps) {
  const t = useTranslations("requirements");
  const tc = useTranslations("common");
  const router = useRouter();

  return (
    <div className="space-y-3">
      <Button
        variant="ghost"
        size="sm"
        className="gap-1 text-muted-foreground"
        onClick={() => router.push("../requirements")}
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToList")}
      </Button>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">
          {requirement.title}
        </h1>
        {requirement.status === "pending" && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="text-green-600 border-green-200 hover:bg-green-50"
              onClick={onConfirm}
            >
              <Check className="mr-1 h-4 w-4" />
              {tc("confirm")}
            </Button>
            <Button
              variant="outline"
              className="text-red-600 border-red-200 hover:bg-red-50"
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
