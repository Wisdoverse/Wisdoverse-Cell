"use client";

import { useTranslations, useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Upload, FileDown, ClipboardList, RefreshCw } from "lucide-react";
import { useSWRConfig } from "swr";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { exportPRD } from "@/lib/api/export";

export function QuickActions() {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const router = useRouter();
  const { mutate } = useSWRConfig();

  async function handleExportPRD() {
    try {
      const result = await exportPRD({ format: "markdown" });
      const blob = new Blob([result.content], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `prd-${result.generated_at || new Date().toISOString().split("T")[0]}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("[quick-actions] PRD export failed:", err);
      toast.error(t("exportFailed"));
    }
  }

  function handleRefresh() {
    mutate(() => true, undefined, { revalidate: true });
  }

  const actions = [
    {
      label: t("uploadMeeting"),
      icon: Upload,
      onClick: () => router.push(`/${locale}/ingest`),
    },
    {
      label: t("exportPRD"),
      icon: FileDown,
      onClick: handleExportPRD,
    },
    {
      label: t("pendingRequirements"),
      icon: ClipboardList,
      onClick: () => router.push(`/${locale}/requirements?status=pending`),
    },
    {
      label: t("refresh"),
      icon: RefreshCw,
      onClick: handleRefresh,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("quickActions")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              className="flex flex-col items-center gap-2 rounded-lg border p-4 transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <action.icon className="h-6 w-6" />
              <span className="text-sm font-medium text-center">
                {action.label}
              </span>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
