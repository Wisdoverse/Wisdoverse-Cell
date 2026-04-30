"use client";

import { useTranslations } from "next-intl";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentDomain } from "@/lib/api/types";
import { DOMAIN_LIST } from "@/lib/registry/domains";

export interface ActivityFilters {
  domain?: AgentDomain;
}

interface ActivityFiltersProps {
  filters: ActivityFilters;
  onFiltersChange: (filters: ActivityFilters) => void;
}

export function ActivityFiltersBar({
  filters,
  onFiltersChange,
}: ActivityFiltersProps) {
  const t = useTranslations("activity");

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select
        value={filters.domain || "all"}
        onValueChange={(v) =>
          onFiltersChange({
            ...filters,
            domain: v === "all" ? undefined : (v as AgentDomain),
          })
        }
      >
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder={t("allDomains")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("allDomains")}</SelectItem>
          {DOMAIN_LIST.map((d) => (
            <SelectItem key={d.id} value={d.id}>
              {d.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
