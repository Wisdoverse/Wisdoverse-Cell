"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";
import useSWR from "swr";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  ClipboardList,
  GitBranch,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import { useControlPlaneAgents } from "@/entities/agent";
import {
  listControlPlaneApprovals,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
  type ControlPlaneAgentRun,
  type ControlPlaneWorkItem,
} from "@/entities/control-plane";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { cn } from "@/lib/utils";
import { summarizeHomeCommandCenter } from "../model/control-plane-home";

function getGreetingKey(): "morning" | "afternoon" | "evening" {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

function formatCurrency(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value > 10 ? 0 : 2,
  }).format(value);
}

function formatNumber(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, {
    notation: value >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatDate(locale: string, value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatRunLabel(run: ControlPlaneAgentRun | undefined): string {
  if (!run) return "-";
  return `${run.agent_id} / ${run.status}`;
}

function metricToneClass(tone: "emerald" | "amber" | "rose" | "indigo") {
  return {
    emerald: "text-emerald-600 dark:text-emerald-400",
    amber: "text-amber-600 dark:text-amber-400",
    rose: "text-rose-600 dark:text-rose-400",
    indigo: "text-indigo-600 dark:text-indigo-400",
  }[tone];
}

function MetricCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "emerald" | "amber" | "rose" | "indigo";
}) {
  return (
    <div className="bg-background/80 min-h-24 rounded-lg border p-4">
      <div
        className={cn(
          "text-3xl leading-none font-semibold tracking-normal tabular-nums",
          metricToneClass(tone),
        )}
      >
        {value}
      </div>
      <p className="text-muted-foreground mt-2 text-sm">{label}</p>
    </div>
  );
}

function PipelineBar({
  label,
  value,
  total,
  className,
}: {
  label: string;
  value: number;
  total: number;
  className: string;
}) {
  const width = total > 0 ? Math.max(4, Math.round((value / total) * 100)) : 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value}</span>
      </div>
      <div className="bg-muted h-2 overflow-hidden rounded-full">
        <div
          className={cn("h-full rounded-full transition-all", className)}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate font-medium tabular-nums">{value}</span>
    </div>
  );
}

function PriorityWorkItem({ workItem }: { workItem: ControlPlaneWorkItem | undefined }) {
  const t = useTranslations("home.commandCenter");
  const locale = useLocale();

  if (!workItem) {
    return (
      <div className="bg-background/60 rounded-lg border border-dashed p-4">
        <p className="text-sm font-medium">{t("queueEmptyTitle")}</p>
        <p className="text-muted-foreground mt-1 text-sm">{t("queueEmptyDescription")}</p>
      </div>
    );
  }

  return (
    <div className="bg-background/80 rounded-lg border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="rounded-md capitalize">
          {workItem.status.replaceAll("_", " ")}
        </Badge>
        <Badge variant="secondary" className="rounded-md capitalize">
          {workItem.priority}
        </Badge>
      </div>
      <p className="mt-3 line-clamp-2 text-sm font-semibold">{workItem.title}</p>
      <div className="text-muted-foreground mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <span>{workItem.owner_agent_id ?? t("unassigned")}</span>
        <span>{formatDate(locale, workItem.updated_at)}</span>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="bg-muted/20 -mx-6 border-y px-6 py-5">
      <div className="space-y-5">
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full rounded-lg" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-48 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function CommandCenter() {
  const t = useTranslations("home");
  const tc = useTranslations("common");
  const locale = useLocale();
  const agentsQuery = useControlPlaneAgents({ limit: 500 });
  const approvalsQuery = useSWR(["home-control-plane-approvals", "pending"], () =>
    listControlPlaneApprovals({ status: "pending", limit: 200 }),
  );
  const runsQuery = useSWR(["home-control-plane-runs", 200], () =>
    listControlPlaneRuns({ limit: 200 }),
  );
  const workItemsQuery = useSWR(["home-control-plane-work-items", 500], () =>
    listControlPlaneWorkItems({ limit: 500 }),
  );

  const agents = useMemo(() => agentsQuery.data?.agents ?? [], [agentsQuery.data?.agents]);
  const approvals = useMemo(
    () => approvalsQuery.data?.approvals ?? [],
    [approvalsQuery.data?.approvals],
  );
  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data?.runs]);
  const workItems = useMemo(
    () => workItemsQuery.data?.work_items ?? [],
    [workItemsQuery.data?.work_items],
  );
  const isLoading =
    agentsQuery.isLoading ||
    approvalsQuery.isLoading ||
    runsQuery.isLoading ||
    workItemsQuery.isLoading;
  const hasError =
    agentsQuery.error || approvalsQuery.error || runsQuery.error || workItemsQuery.error;
  const summary = useMemo(
    () =>
      summarizeHomeCommandCenter({
        agents,
        approvals,
        runs,
        workItems,
      }),
    [agents, approvals, runs, workItems],
  );
  const goalCoverage =
    summary.openWorkCount > 0
      ? Math.round((summary.goalLinkedWorkCount / summary.openWorkCount) * 100)
      : 100;

  if (isLoading) return <LoadingState />;

  return (
    <section className="bg-muted/20 -mx-6 border-y px-6 py-5">
      <div className="space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <Badge variant="outline" className="rounded-md">
              {t("commandCenter.badge")}
            </Badge>
            <h1 className="mt-3 text-2xl font-semibold tracking-normal">
              {t(`greeting.${getGreetingKey()}`)}
            </h1>
            <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
              {t("commandCenter.description")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={`/${locale}/workflows`}>
                <Workflow className="size-4" />
                {t("commandCenter.actions.workflows")}
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={`/${locale}/agents`}>
                <Bot className="size-4" />
                {t("commandCenter.actions.agents")}
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link href={`/${locale}/approvals`}>
                <ShieldCheck className="size-4" />
                {t("commandCenter.actions.approvals")}
              </Link>
            </Button>
          </div>
        </div>

        {hasError ? (
          <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-lg border p-4 text-sm">
            {tc("error")}
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCell label={t("stats.running")} value={summary.runningCount} tone="emerald" />
          <MetricCell label={t("stats.attention")} value={summary.attentionCount} tone="amber" />
          <MetricCell label={t("stats.errors")} value={summary.errorCount} tone="rose" />
          <MetricCell
            label={t("stats.pendingApprovals")}
            value={summary.pendingApprovalCount}
            tone="indigo"
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.9fr_0.95fr]">
          <div className="bg-background/80 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">{t("commandCenter.workflowTitle")}</h2>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t("commandCenter.workflowDescription", {
                    count: summary.openWorkCount,
                  })}
                </p>
              </div>
              <ClipboardList className="text-muted-foreground size-4" />
            </div>
            <div className="mt-5 space-y-4">
              <PipelineBar
                label={t("commandCenter.runningWork")}
                value={summary.runningWorkCount}
                total={summary.openWorkCount}
                className="bg-emerald-500"
              />
              <PipelineBar
                label={t("commandCenter.readyWork")}
                value={summary.readyWorkCount}
                total={summary.openWorkCount}
                className="bg-sky-500"
              />
              <PipelineBar
                label={t("commandCenter.approvalWork")}
                value={summary.approvalWorkCount}
                total={summary.openWorkCount}
                className="bg-amber-500"
              />
              <PipelineBar
                label={t("commandCenter.blockedWork")}
                value={summary.blockedWorkCount}
                total={Math.max(summary.openWorkCount, summary.blockedWorkCount)}
                className="bg-rose-500"
              />
            </div>
          </div>

          <div className="bg-background/80 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">{t("commandCenter.priorityTitle")}</h2>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t("commandCenter.priorityDescription")}
                </p>
              </div>
              <ArrowRight className="text-muted-foreground size-4" />
            </div>
            <div className="mt-4">
              <PriorityWorkItem workItem={summary.priorityWorkItem} />
            </div>
          </div>

          <div className="bg-background/80 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">{t("commandCenter.evidenceTitle")}</h2>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t("commandCenter.evidenceDescription")}
                </p>
              </div>
              <GitBranch className="text-muted-foreground size-4" />
            </div>
            <div className="mt-5 space-y-3">
              <DetailRow label={t("commandCenter.activeAgents")} value={`${summary.agentCount}`} />
              <DetailRow label={t("commandCenter.goalCoverage")} value={`${goalCoverage}%`} />
              <DetailRow
                label={t("commandCenter.latestRun")}
                value={formatRunLabel(summary.latestRun)}
              />
              <DetailRow
                label={t("commandCenter.runCost")}
                value={formatCurrency(locale, summary.runCostUsd)}
              />
              <DetailRow
                label={t("commandCenter.tokens")}
                value={formatNumber(locale, summary.tokenCount)}
              />
            </div>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <div className="bg-muted/60 rounded-lg p-3">
                <CheckCircle2 className="mb-2 size-4 text-emerald-600" />
                <div className="text-lg font-semibold tabular-nums">
                  {summary.completedRunCount}
                </div>
                <p className="text-muted-foreground text-xs">{t("commandCenter.completedRuns")}</p>
              </div>
              <div className="bg-muted/60 rounded-lg p-3">
                <CircleDollarSign className="text-muted-foreground mb-2 size-4" />
                <div className="text-lg font-semibold tabular-nums">
                  {summary.unassignedWorkCount}
                </div>
                <p className="text-muted-foreground text-xs">{t("commandCenter.unassignedWork")}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
