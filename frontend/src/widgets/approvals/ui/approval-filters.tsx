"use client";

import { useTranslations } from "next-intl";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { Badge } from "@/shared/ui/badge";

interface ApprovalFiltersProps {
  activeType: string | undefined;
  onTypeChange: (type: string | undefined) => void;
  counts: Record<string, number>;
}

const APPROVAL_TABS = ["all", "finance", "legal", "technical", "customer"] as const;

export function ApprovalFilters({ activeType, onTypeChange, counts }: ApprovalFiltersProps) {
  const t = useTranslations("approvals");

  return (
    <Tabs
      value={activeType ?? "all"}
      onValueChange={(value) => onTypeChange(value === "all" ? undefined : value)}
    >
      <TabsList className="h-auto w-full flex-wrap justify-start">
        {APPROVAL_TABS.map((tab) => (
          <TabsTrigger key={tab} value={tab} className="flex-none">
            {t(tab)}
            <Badge variant="secondary" className="ml-1.5 px-1.5 text-[10px]">
              {counts[tab] ?? 0}
            </Badge>
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
