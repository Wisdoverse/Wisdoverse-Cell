"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import type { ColumnDef } from "@tanstack/react-table";
import { Check, X } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { DataTable } from "@/shared/ui/data-table";
import { StatusBadge } from "@/entities/requirement/ui/status-badge";
import { PriorityBadge } from "@/entities/requirement/ui/priority-badge";
import type { Requirement } from "@/lib/api/types";

interface RequirementsTableProps {
  data: Requirement[];
  isLoading: boolean;
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}

function useMobileRequirementsList(): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;

    const query = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return isMobile;
}

function RequirementActions({
  requirement,
  onConfirm,
  onReject,
  t,
  tc,
}: {
  requirement: Requirement;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
  tc: (key: string) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      <Button
        variant="outline"
        size="xs"
        className="text-green-600 hover:bg-green-50 hover:text-green-700"
        aria-label={t("confirmRequirement", { title: requirement.title })}
        onClick={(event) => {
          event.stopPropagation();
          onConfirm(requirement.id);
        }}
      >
        <Check className="h-4 w-4" />
        {tc("confirm")}
      </Button>
      <Button
        variant="outline"
        size="xs"
        className="text-red-600 hover:bg-red-50 hover:text-red-700"
        aria-label={t("rejectRequirement", { title: requirement.title })}
        onClick={(event) => {
          event.stopPropagation();
          onReject(requirement.id);
        }}
      >
        <X className="h-4 w-4" />
        {tc("reject")}
      </Button>
    </div>
  );
}

export function RequirementsTable({
  data,
  isLoading,
  page,
  pageSize,
  total,
  onPageChange,
  selectedIds,
  onSelectionChange,
  onConfirm,
  onReject,
}: RequirementsTableProps) {
  const t = useTranslations("requirements");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const isMobile = useMobileRequirementsList();

  const toggleSelection = (id: string) => {
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((s) => s !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  const toggleAll = () => {
    if (selectedIds.length === data.length) {
      onSelectionChange([]);
    } else {
      onSelectionChange(data.map((r) => r.id));
    }
  };

  const columns: ColumnDef<Requirement, unknown>[] = [
    {
      id: "select",
      header: () => (
        <input
          type="checkbox"
          aria-label={t("selectAll")}
          checked={data.length > 0 && selectedIds.length === data.length}
          onChange={toggleAll}
          className="h-4 w-4 rounded border-gray-300"
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label={t("selectRequirement", { title: row.original.title })}
          checked={selectedIds.includes(row.original.id)}
          onChange={(e) => {
            e.stopPropagation();
            toggleSelection(row.original.id);
          }}
          className="h-4 w-4 rounded border-gray-300"
        />
      ),
      size: 40,
    },
    {
      accessorKey: "title",
      header: t("title"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <div className="truncate font-medium">{row.original.title}</div>
          {row.original.open_questions.length > 0 && (
            <div className="text-muted-foreground mt-1 text-xs">
              {t("openQuestionCount", { count: row.original.open_questions.length })}
            </div>
          )}
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: t("status"),
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
      size: 120,
    },
    {
      accessorKey: "priority",
      header: t("priority"),
      cell: ({ row }) => <PriorityBadge priority={row.original.priority} />,
      size: 100,
    },
    {
      accessorKey: "category",
      header: t("category"),
      cell: ({ row }) => <Badge variant="secondary">{row.original.category}</Badge>,
      size: 100,
    },
    {
      accessorKey: "created_at",
      header: t("createdAt"),
      cell: ({ row }) => (
        <span className="text-muted-foreground text-sm">
          {new Date(row.original.created_at).toLocaleDateString(locale)}
        </span>
      ),
      size: 120,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <RequirementActions
          requirement={row.original}
          onConfirm={onConfirm}
          onReject={onReject}
          t={t}
          tc={tc}
        />
      ),
      size: 160,
    },
  ];

  if (isMobile) {
    if (isLoading) {
      return (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="bg-muted h-32 animate-pulse rounded-lg border" />
          ))}
        </div>
      );
    }

    if (data.length === 0) {
      return (
        <div className="text-muted-foreground rounded-lg border py-12 text-center text-sm">
          {tc("noData")}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {data.map((requirement) => (
          <div key={requirement.id} className="bg-card rounded-lg border p-4">
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                aria-label={t("selectRequirement", {
                  title: requirement.title,
                })}
                checked={selectedIds.includes(requirement.id)}
                onChange={() => toggleSelection(requirement.id)}
                className="mt-1 h-4 w-4 shrink-0 rounded border-gray-300"
              />
              <div className="min-w-0 flex-1 space-y-3">
                <button
                  type="button"
                  className="block w-full text-left text-sm leading-5 font-semibold"
                  onClick={() => router.push(`requirements/${requirement.id}`)}
                >
                  {requirement.title}
                </button>

                <div className="flex flex-wrap gap-1.5">
                  <StatusBadge status={requirement.status} />
                  <PriorityBadge priority={requirement.priority} />
                  <Badge variant="secondary">{requirement.category}</Badge>
                </div>

                <div className="text-muted-foreground space-y-1 text-xs">
                  <p>
                    {t("createdAt")}: {new Date(requirement.created_at).toLocaleDateString(locale)}
                  </p>
                  {requirement.open_questions.length > 0 && (
                    <p>
                      {t("openQuestionCount", {
                        count: requirement.open_questions.length,
                      })}
                    </p>
                  )}
                </div>

                <RequirementActions
                  requirement={requirement}
                  onConfirm={onConfirm}
                  onReject={onReject}
                  t={t}
                  tc={tc}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <DataTable
      columns={columns}
      data={data}
      isLoading={isLoading}
      page={page}
      pageSize={pageSize}
      total={total}
      onPageChange={onPageChange}
      onRowClick={(row) => router.push(`requirements/${row.id}`)}
    />
  );
}
