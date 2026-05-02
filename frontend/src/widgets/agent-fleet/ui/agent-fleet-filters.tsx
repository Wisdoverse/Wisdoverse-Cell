"use client";

import { Search } from "lucide-react";
import { useTranslations } from "next-intl";

import type { AgentStatus } from "@/entities/agent";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface AgentFleetFiltersState {
  status: AgentStatus | "all";
  search: string;
}

interface AgentFleetFiltersProps {
  filters: AgentFleetFiltersState;
  onFiltersChange: (filters: AgentFleetFiltersState) => void;
}

const STATUS_OPTIONS = ["all", "running", "idle", "error", "stopped"] as const;

export function AgentFleetFilters({
  filters,
  onFiltersChange,
}: AgentFleetFiltersProps) {
  const t = useTranslations("agents");

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative max-w-sm flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={t("searchPlaceholder")}
          value={filters.search}
          onChange={(event) =>
            onFiltersChange({ ...filters, search: event.target.value })
          }
          className="pl-9"
        />
      </div>

      <div className="flex items-center gap-1 rounded-lg border bg-muted/50 p-1">
        {STATUS_OPTIONS.map((status) => (
          <button
            key={status}
            onClick={() =>
              onFiltersChange({
                ...filters,
                status: status as AgentStatus | "all",
              })
            }
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              filters.status === status
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t(status)}
          </button>
        ))}
      </div>
    </div>
  );
}
