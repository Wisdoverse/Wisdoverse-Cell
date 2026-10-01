"use client";

import { useTranslations } from "next-intl";

import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Textarea } from "@/shared/ui/textarea";

export function AgentExecutionPolicyFields({
  adapterType,
  permissions,
  maxCostUsd,
  onPermissionsChange,
  onMaxCostChange,
}: {
  adapterType: string;
  permissions: string;
  maxCostUsd: string;
  onPermissionsChange: (value: string) => void;
  onMaxCostChange: (value: string) => void;
}) {
  const t = useTranslations("executionPolicy");
  const requiredPermissions = ["work.execute", `adapter:${adapterType}`, "tool:wakeup"];
  return (
    <section className="space-y-4 rounded-lg border border-amber-300/70 bg-amber-50/50 p-4 dark:border-amber-900/50 dark:bg-amber-950/20 md:col-span-2">
      <div>
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{t("description")}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="agent-execution-permissions">{t("permissionsLabel")}</Label>
          <Textarea
            id="agent-execution-permissions"
            value={permissions}
            onChange={(event) => onPermissionsChange(event.target.value)}
            placeholder={requiredPermissions.join("\n")}
            rows={4}
          />
          <p className="text-xs leading-5 text-muted-foreground">
            {t("requiredPermissions")}: <code>{requiredPermissions.join(", ")}</code>
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="agent-execution-max-cost">{t("maxCostLabel")}</Label>
          <Input
            id="agent-execution-max-cost"
            type="number"
            min="0"
            max="1000000"
            step="0.000001"
            required={adapterType !== "builtin"}
            value={maxCostUsd}
            onChange={(event) => onMaxCostChange(event.target.value)}
          />
          <p className="text-xs leading-5 text-muted-foreground">{t("budgetRequirement")}</p>
        </div>
      </div>
    </section>
  );
}
