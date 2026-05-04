"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ColumnDef } from "@tanstack/react-table";
import { Check, X } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { DataTable } from "@/shared/ui/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { PriorityBadge } from "@/components/shared/priority-badge";
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
  const router = useRouter();

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
          checked={data.length > 0 && selectedIds.length === data.length}
          onChange={toggleAll}
          className="h-4 w-4 rounded border-gray-300"
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
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
        <span className="font-medium">{row.original.title}</span>
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
      cell: ({ row }) => (
        <Badge variant="secondary">{row.original.category}</Badge>
      ),
      size: 100,
    },
    {
      accessorKey: "created_at",
      header: t("createdAt"),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {new Date(row.original.created_at).toLocaleDateString()}
        </span>
      ),
      size: 120,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-green-600 hover:text-green-700 hover:bg-green-50"
            onClick={(e) => {
              e.stopPropagation();
              onConfirm(row.original.id);
            }}
          >
            <Check className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
            onClick={(e) => {
              e.stopPropagation();
              onReject(row.original.id);
            }}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ),
      size: 80,
    },
  ];

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
