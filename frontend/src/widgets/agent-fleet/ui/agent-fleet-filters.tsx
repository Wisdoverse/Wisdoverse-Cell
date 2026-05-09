"use client";

import { Search } from "lucide-react";
import { useTranslations } from "next-intl";

import type { AgentKind, AgentStatus } from "@/entities/agent";
import { Input } from "@/shared/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { cn } from "@/lib/utils";

export interface AgentFleetFiltersState {
  status: AgentStatus | "all";
  agentKind: AgentKind | "all";
  search: string;
}

interface AgentFleetFiltersProps {
  filters: AgentFleetFiltersState;
  onFiltersChange: (filters: AgentFleetFiltersState) => void;
}

const STATUS_OPTIONS = [
  "all",
  "running",
  "idle",
  "paused",
  "error",
  "stopped",
] as const;
const AGENT_KIND_OPTIONS = [
  "all",
  "organization_role",
  "business_runtime_agent",
  "integration_gateway",
  "capability_module",
  "system_worker",
] as const;

export function AgentFleetFilters({
  filters,
  onFiltersChange,
}: AgentFleetFiltersProps) {
  const t = useTranslations("agents");

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
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

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Select
          value={filters.agentKind}
          onValueChange={(agentKind) =>
            onFiltersChange({
              ...filters,
              agentKind: agentKind as AgentKind | "all",
            })
          }
        >
          <SelectTrigger className="w-full sm:w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AGENT_KIND_OPTIONS.map((agentKind) => (
              <SelectItem key={agentKind} value={agentKind}>
                {agentKind === "all"
                  ? t("allKinds")
                  : t(`agentKinds.${agentKind}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

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
    </div>
  );
}
