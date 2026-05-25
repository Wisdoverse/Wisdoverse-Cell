"use client";

import { useLocale, useTranslations } from "next-intl";
import type { ApprovalRequest } from "@/lib/api/types";
import { AgentDisplayAvatar, AGENT_REGISTRY, DomainBadge } from "@/entities/agent";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import {
  AlertTriangle,
  Check,
  ExternalLink,
  MessageCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ApprovalCardProps {
  approval: ApprovalRequest;
  onApprove?: () => void;
  onReject?: () => void;
  onAsk?: () => void;
  className?: string;
}

function formatTimeAgo(dateStr: string, locale: string): string {
  const diff = new Date(dateStr).getTime() - Date.now();
  if (Number.isNaN(diff)) return dateStr;

  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const minutes = Math.round(diff / 60000);
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(hours / 24), "day");
}

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof AlertTriangle;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 gap-2 text-sm">
      <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">
        <div className="text-muted-foreground text-xs">{label}</div>
        <div className="line-clamp-2">{value}</div>
      </div>
    </div>
  );
}

export function ApprovalCard({
  approval,
  onApprove,
  onReject,
  onAsk,
  className,
}: ApprovalCardProps) {
  const t = useTranslations("approvals");
  const locale = useLocale();
  const agentMeta = AGENT_REGISTRY[approval.source_agent_id];
  const affectedResources = approval.affected_resources ?? [];

  return (
    <div
      className={cn(
        "space-y-4 rounded-lg border bg-card p-4",
        approval.urgency === "urgent" && "border-red-300 dark:border-red-800",
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {agentMeta && (
            <AgentDisplayAvatar
              domain={agentMeta.domain}
              icon={agentMeta.icon}
              shortName={agentMeta.shortName}
              size="sm"
            />
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate">{approval.title}</div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{agentMeta?.name ?? approval.source_agent_id}</span>
              {agentMeta && <DomainBadge domain={agentMeta.domain} />}
              <Badge variant="secondary" className="h-5 rounded-md px-1.5 text-[10px]">
                {t(approval.approval_type)}
              </Badge>
            </div>
          </div>
        </div>
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {formatTimeAgo(approval.created_at, locale)}
        </span>
      </div>

      <p className="text-sm text-muted-foreground">{approval.summary}</p>

      <div className="grid gap-3 rounded-lg bg-muted/40 p-3 md:grid-cols-2">
        {approval.risk ? (
          <InfoRow icon={AlertTriangle} label={t("risk")} value={approval.risk} />
        ) : null}
        {approval.rollback_note ? (
          <InfoRow icon={RotateCcw} label={t("rollback")} value={approval.rollback_note} />
        ) : null}
        {affectedResources.length > 0 ? (
          <div className="min-w-0 md:col-span-2">
            <div className="text-muted-foreground text-xs">{t("affectedResources")}</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {affectedResources.map((resource) => (
                <Badge key={resource} variant="outline" className="rounded-md">
                  {resource}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {approval.context_link ? (
        <a
          href={approval.context_link}
          className="text-primary inline-flex items-center gap-1 text-sm font-medium"
        >
          <ExternalLink className="size-3.5" />
          {t("viewEvidence")}
        </a>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={onApprove} className="gap-1" aria-label={t("approve")}>
          <Check className="h-3.5 w-3.5" />
          {t("approve")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onReject}
          className="gap-1 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950"
          aria-label={t("reject")}
        >
          <X className="h-3.5 w-3.5" />
          {t("reject")}
        </Button>
        {onAsk && (
          <Button size="sm" variant="ghost" onClick={onAsk} className="gap-1" aria-label={t("ask")}>
            <MessageCircle className="h-3.5 w-3.5" />
            {t("ask")}
          </Button>
        )}
      </div>
    </div>
  );
}
