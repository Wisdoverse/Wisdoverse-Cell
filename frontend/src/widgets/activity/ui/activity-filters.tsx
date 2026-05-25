"use client";

import { useTranslations } from "next-intl";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { DOMAIN_LIST, getDomainLabelKey, type AgentDomain } from "@/entities/agent";

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
  const ta = useTranslations("agents");

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
              {ta(`domainLabels.${getDomainLabelKey(d.id)}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
