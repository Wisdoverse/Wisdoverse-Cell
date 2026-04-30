"use client";

import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Category, RequirementFilters } from "@/lib/api/types";

interface RequirementsFiltersProps {
  filters: RequirementFilters;
  onFiltersChange: (filters: RequirementFilters) => void;
}

const CATEGORY_I18N_KEYS: Record<Category, string> = {
  "功能": "categoryFunction",
  "性能": "categoryPerformance",
  "硬件": "categoryHardware",
  "集成": "categoryIntegration",
  "UI": "categoryUI",
  "安全": "categorySecurity",
  "其他": "categoryOther",
};

const CATEGORIES = Object.keys(CATEGORY_I18N_KEYS) as Category[];

export function RequirementsFilters({
  filters,
  onFiltersChange,
}: RequirementsFiltersProps) {
  const t = useTranslations("requirements");

  const updateFilter = (key: keyof RequirementFilters, value: string) => {
    const newFilters = { ...filters, page: 1 };
    if (value === "all") {
      delete newFilters[key];
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (newFilters as any)[key] = value;
    }
    onFiltersChange(newFilters);
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select
        value={filters.status || "all"}
        onValueChange={(v) => updateFilter("status", v)}
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder={t("allStatus")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("allStatus")}</SelectItem>
          <SelectItem value="pending">{t("statusPending")}</SelectItem>
          <SelectItem value="confirmed">{t("statusConfirmed")}</SelectItem>
          <SelectItem value="rejected">{t("statusRejected")}</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={filters.priority || "all"}
        onValueChange={(v) => updateFilter("priority", v)}
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder={t("allPriority")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("allPriority")}</SelectItem>
          <SelectItem value="high">{t("priorityHigh")}</SelectItem>
          <SelectItem value="medium">{t("priorityMedium")}</SelectItem>
          <SelectItem value="low">{t("priorityLow")}</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={filters.category || "all"}
        onValueChange={(v) => updateFilter("category", v)}
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder={t("allCategory")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("allCategory")}</SelectItem>
          {CATEGORIES.map((cat) => (
            <SelectItem key={cat} value={cat}>
              {t(CATEGORY_I18N_KEYS[cat])}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Input
        placeholder={t("semanticSearch")}
        className="w-[240px]"
      />
    </div>
  );
}
