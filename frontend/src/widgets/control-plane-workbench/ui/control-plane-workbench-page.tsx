"use client";

import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  AlertCircle,
  Archive,
  Check,
  CheckCircle2,
  CircleDollarSign,
  FileText,
  GitBranch,
  Loader2,
  PanelRightOpen,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
} from "lucide-react";

import {
  useControlPlaneWorkbench,
  type ControlPlaneAgentRun,
  type ControlPlaneApproval,
  type ControlPlaneArtifact,
  type ControlPlaneBudgetPolicy,
  type ControlPlaneDecision,
  type ControlPlaneEvolutionProposal,
  type ControlPlaneGoal,
  type ControlPlaneTimelineItem,
  type ControlPlaneWorkbenchState,
  type BudgetPeriod,
  type BudgetPolicyStatus,
  type BudgetScope,
  type WorkItemPriority,
} from "@/entities/control-plane";
import { EmptyState } from "@/shared/ui/empty-state";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Skeleton } from "@/shared/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/ui/tabs";
import { Textarea } from "@/shared/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui/table";
import { cn } from "@/lib/utils";

type Workbench = ControlPlaneWorkbenchState;

const priorityClass: Record<WorkItemPriority, string> = {
  low: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-300",
  medium:
    "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-300",
  high: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-300",
  critical:
    "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-300",
};

const statusClass: Record<string, string> = {
  active: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-300",
  approved:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-300",
  running:
    "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-300",
  succeeded:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-300",
  completed:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-300",
  proposed:
    "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900/70 dark:bg-violet-950/30 dark:text-violet-300",
  pending:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-300",
  shadow:
    "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-300",
  canary:
    "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-900/70 dark:bg-indigo-950/30 dark:text-indigo-300",
  awaiting_approval:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-300",
  blocked:
    "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-300",
  failed:
    "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-300",
  rejected:
    "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-300",
  rolled_back:
    "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-300",
  cancelled:
    "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300",
  draft:
    "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300",
};

const timelineAccentClass: Record<string, string> = {
  agent_run: "bg-sky-500",
  decision: "bg-violet-500",
  artifact: "bg-cyan-500",
  approval: "bg-amber-500",
  budget_usage: "bg-emerald-500",
  audit_event: "bg-zinc-400",
};

const budgetScopes: BudgetScope[] = ["company", "goal", "agent", "work_item"];
const budgetPeriods: BudgetPeriod[] = ["daily", "monthly", "quarterly", "total"];
const budgetStatuses: BudgetPolicyStatus[] = ["active", "paused", "archived"];

function getString(
  data: Record<string, unknown>,
  keys: string[],
  fallback: string,
): string {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return fallback;
}

function formatCost(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function parseModelAllowlist(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function StatusBadge({ value }: { value: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 rounded-md px-2 text-[11px] font-medium capitalize",
        statusClass[value] ??
          "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300",
      )}
    >
      {value.replaceAll("_", " ")}
    </Badge>
  );
}

function WorkPriorityBadge({ priority }: { priority: WorkItemPriority }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 rounded-md px-2 text-[11px] font-medium capitalize",
        priorityClass[priority],
      )}
    >
      {priority}
    </Badge>
  );
}

function progressValue(goal: ControlPlaneGoal): number | undefined {
  if (
    goal.current_value == null ||
    goal.target_value == null ||
    goal.target_value <= 0
  ) {
    return undefined;
  }
  return Math.max(
    0,
    Math.min(100, (goal.current_value / goal.target_value) * 100),
  );
}

function SummaryMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: typeof Workflow;
}) {
  return (
    <div className="flex h-20 items-center justify-between rounded-lg border border-white/70 bg-white/70 px-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/50">
      <div>
        <div className="text-[1.65rem] font-semibold leading-none tracking-normal tabular-nums">
          {value}
        </div>
        <div className="mt-2 text-[11px] font-medium uppercase text-muted-foreground">
          {label}
        </div>
      </div>
      <div className="flex size-9 items-center justify-center rounded-lg border border-zinc-200/70 bg-white/80 text-zinc-600 dark:border-white/10 dark:bg-white/5 dark:text-zinc-300">
        <Icon className="size-4" />
      </div>
    </div>
  );
}

function ColumnShell({
  title,
  icon: Icon,
  action,
  children,
  className,
}: {
  title: string;
  icon: typeof Workflow;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "min-h-[560px] overflow-hidden rounded-lg border border-white/70 bg-white/80 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/50 dark:shadow-none",
        className,
      )}
    >
      <div className="flex h-[3.25rem] items-center justify-between border-b border-zinc-200/70 px-4 dark:border-white/10">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-zinc-950 text-white dark:bg-white dark:text-zinc-950">
            <Icon className="size-3.5" />
          </div>
          <h2 className="text-sm font-semibold">{title}</h2>
        </div>
        {action}
      </div>
      <div className="h-[calc(100%-3.25rem)] overflow-y-auto p-3">{children}</div>
    </section>
  );
}

function CreateGoalDialog({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ownerAgentId, setOwnerAgentId] = useState("pjm-agent");
  const isCreating = workbench.goalActionId === "create";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedTitle = title.trim();
    if (!cleanedTitle) return;
    await workbench.createGoal({
      title: cleanedTitle,
      description: description.trim(),
      owner_agent_id: ownerAgentId.trim() || undefined,
    });
    setTitle("");
    setDescription("");
    setOwnerAgentId("pjm-agent");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="xs">
          <Plus className="size-3.5" />
          {t("newGoal")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("newGoal")}</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="space-y-2">
            <Label htmlFor="control-plane-goal-title">{t("goalTitle")}</Label>
            <Input
              id="control-plane-goal-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="control-plane-goal-description">
              {t("description")}
            </Label>
            <Textarea
              id="control-plane-goal-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="control-plane-goal-owner">{t("ownerAgent")}</Label>
            <Input
              id="control-plane-goal-owner"
              value={ownerAgentId}
              onChange={(event) => setOwnerAgentId(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={isCreating || !title.trim()}>
              {isCreating ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {isCreating ? t("creating") : t("create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CreateWorkItemDialog({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ownerAgentId, setOwnerAgentId] = useState("dev-agent");
  const isCreating = workbench.workItemActionId === "create";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedTitle = title.trim();
    if (!cleanedTitle) return;
    await workbench.createWorkItem({
      title: cleanedTitle,
      description: description.trim(),
      owner_agent_id: ownerAgentId.trim() || undefined,
    });
    setTitle("");
    setDescription("");
    setOwnerAgentId("dev-agent");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="xs" disabled={!workbench.activeGoalId}>
          <Plus className="size-3.5" />
          {t("newWorkItem")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("newWorkItem")}</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="space-y-2">
            <Label htmlFor="control-plane-work-title">{t("workItemTitle")}</Label>
            <Input
              id="control-plane-work-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="control-plane-work-description">
              {t("description")}
            </Label>
            <Textarea
              id="control-plane-work-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="control-plane-work-owner">{t("ownerAgent")}</Label>
            <Input
              id="control-plane-work-owner"
              value={ownerAgentId}
              onChange={(event) => setOwnerAgentId(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={isCreating || !title.trim()}>
              {isCreating ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {isCreating ? t("creating") : t("create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PolicySelect<T extends string>({
  id,
  value,
  values,
  onChange,
}: {
  id: string;
  value: T;
  values: T[];
  onChange: (value: T) => void;
}) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next as T)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {values.map((item) => (
          <SelectItem key={item} value={item}>
            {item.replaceAll("_", " ")}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function CreateBudgetPolicyDialog({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<BudgetScope>("agent");
  const [scopeId, setScopeId] = useState("dev-agent");
  const [period, setPeriod] = useState<BudgetPeriod>("daily");
  const [status, setStatus] = useState<BudgetPolicyStatus>("active");
  const [limitUsd, setLimitUsd] = useState("10");
  const [warningThreshold, setWarningThreshold] = useState("0.8");
  const [modelAllowlist, setModelAllowlist] = useState("");
  const isCreating = workbench.budgetPolicyActionId === "create";
  const scopeNeedsId = scope !== "company";
  const parsedLimit = Number(limitUsd);
  const parsedThreshold = Number(warningThreshold);
  const isInvalid =
    !Number.isFinite(parsedLimit) ||
    parsedLimit <= 0 ||
    !Number.isFinite(parsedThreshold) ||
    parsedThreshold <= 0 ||
    parsedThreshold > 1 ||
    (scopeNeedsId && !scopeId.trim());

  function resetForm() {
    setScope("agent");
    setScopeId("dev-agent");
    setPeriod("daily");
    setStatus("active");
    setLimitUsd("10");
    setWarningThreshold("0.8");
    setModelAllowlist("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isInvalid) return;
    await workbench.createBudgetPolicy({
      scope,
      scope_id: scopeNeedsId ? scopeId.trim() : undefined,
      period,
      status,
      limit_usd: parsedLimit,
      warning_threshold: parsedThreshold,
      model_allowlist: parseModelAllowlist(modelAllowlist),
    });
    resetForm();
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="xs">
          <Plus className="size-3.5" />
          {t("newBudgetPolicy")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("newBudgetPolicy")}</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="control-plane-budget-scope">{t("scope")}</Label>
              <PolicySelect
                id="control-plane-budget-scope"
                value={scope}
                values={budgetScopes}
                onChange={(value) => {
                  setScope(value);
                  setScopeId(value === "company" ? "" : scopeId || "dev-agent");
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="control-plane-budget-period">{t("period")}</Label>
              <PolicySelect
                id="control-plane-budget-period"
                value={period}
                values={budgetPeriods}
                onChange={setPeriod}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="control-plane-budget-status">{t("status")}</Label>
              <PolicySelect
                id="control-plane-budget-status"
                value={status}
                values={budgetStatuses}
                onChange={setStatus}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="control-plane-budget-scope-id">
                {t("scopeId")}
              </Label>
              <Input
                id="control-plane-budget-scope-id"
                value={scopeId}
                onChange={(event) => setScopeId(event.target.value)}
                disabled={!scopeNeedsId}
                required={scopeNeedsId}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="control-plane-budget-limit">
                {t("budgetLimit")}
              </Label>
              <Input
                id="control-plane-budget-limit"
                type="number"
                min="0.01"
                step="0.01"
                value={limitUsd}
                onChange={(event) => setLimitUsd(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="control-plane-budget-threshold">
                {t("warningThreshold")}
              </Label>
              <Input
                id="control-plane-budget-threshold"
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={warningThreshold}
                onChange={(event) => setWarningThreshold(event.target.value)}
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="control-plane-budget-models">
              {t("modelAllowlist")}
            </Label>
            <Input
              id="control-plane-budget-models"
              value={modelAllowlist}
              onChange={(event) => setModelAllowlist(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={isCreating || isInvalid}>
              {isCreating ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {isCreating ? t("creating") : t("create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditBudgetPolicyDialog({
  policy,
  workbench,
}: {
  policy: ControlPlaneBudgetPolicy;
  workbench: Workbench;
}) {
  const t = useTranslations("controlPlane");
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<BudgetPolicyStatus>(policy.status);
  const [limitUsd, setLimitUsd] = useState(String(policy.limit_usd));
  const [warningThreshold, setWarningThreshold] = useState(
    String(policy.warning_threshold),
  );
  const [modelAllowlist, setModelAllowlist] = useState(
    policy.model_allowlist.join(", "),
  );
  const isSaving = workbench.budgetPolicyActionId === policy.budget_id;
  const parsedLimit = Number(limitUsd);
  const parsedThreshold = Number(warningThreshold);
  const isInvalid =
    !Number.isFinite(parsedLimit) ||
    parsedLimit <= 0 ||
    !Number.isFinite(parsedThreshold) ||
    parsedThreshold <= 0 ||
    parsedThreshold > 1;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isInvalid) return;
    await workbench.updateBudgetPolicy(policy.budget_id, {
      status,
      limit_usd: parsedLimit,
      warning_threshold: parsedThreshold,
      model_allowlist: parseModelAllowlist(modelAllowlist),
    });
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="xs">
          <Pencil className="size-3" />
          {t("edit")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("editBudgetPolicy")}</DialogTitle>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor={`control-plane-budget-edit-status-${policy.budget_id}`}>
                {t("status")}
              </Label>
              <PolicySelect
                id={`control-plane-budget-edit-status-${policy.budget_id}`}
                value={status}
                values={budgetStatuses}
                onChange={setStatus}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`control-plane-budget-edit-limit-${policy.budget_id}`}>
                {t("budgetLimit")}
              </Label>
              <Input
                id={`control-plane-budget-edit-limit-${policy.budget_id}`}
                type="number"
                min="0.01"
                step="0.01"
                value={limitUsd}
                onChange={(event) => setLimitUsd(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label
                htmlFor={`control-plane-budget-edit-threshold-${policy.budget_id}`}
              >
                {t("warningThreshold")}
              </Label>
              <Input
                id={`control-plane-budget-edit-threshold-${policy.budget_id}`}
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={warningThreshold}
                onChange={(event) => setWarningThreshold(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`control-plane-budget-edit-models-${policy.budget_id}`}>
                {t("modelAllowlist")}
              </Label>
              <Input
                id={`control-plane-budget-edit-models-${policy.budget_id}`}
                value={modelAllowlist}
                onChange={(event) => setModelAllowlist(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={isSaving || isInvalid}>
              {isSaving ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Check className="size-4" />
              )}
              {isSaving ? t("saving") : t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BudgetPolicyPanel({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const locale = useLocale();

  return (
    <section className="rounded-lg border border-white/70 bg-white/80 p-4 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/50 dark:shadow-none">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-zinc-950 text-white dark:bg-white dark:text-zinc-950">
            <CircleDollarSign className="size-3.5" />
          </div>
          <h2 className="truncate text-sm font-semibold">
            {t("budgetPolicies")}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-6 rounded-md px-2 text-[11px]">
            {workbench.budgetPolicies.length}
          </Badge>
          <CreateBudgetPolicyDialog workbench={workbench} />
        </div>
      </div>

      {workbench.isBudgetPolicyLoading ? (
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton
              key={index}
              className="h-32 rounded-lg bg-white/60 dark:bg-white/10"
            />
          ))}
        </div>
      ) : workbench.budgetPolicies.length === 0 ? (
        <EmptyState message={t("noBudgetPolicies")} />
      ) : (
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {workbench.budgetPolicies.map((policy) => (
            <BudgetPolicyItem
              key={policy.budget_id}
              policy={policy}
              locale={locale}
              workbench={workbench}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function BudgetPolicyItem({
  policy,
  locale,
  workbench,
}: {
  policy: ControlPlaneBudgetPolicy;
  locale: string;
  workbench: Workbench;
}) {
  const t = useTranslations("controlPlane");
  const isMutating = workbench.budgetPolicyActionId === policy.budget_id;
  const nextStatus: BudgetPolicyStatus =
    policy.status === "active" ? "paused" : "active";
  const canToggle = policy.status !== "archived";

  return (
    <div className="rounded-lg border border-zinc-200/80 bg-white/75 px-3 py-3 shadow-[0_1px_1px_rgba(15,23,42,0.03)] dark:border-white/10 dark:bg-white/[0.035]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold leading-5">
            {policy.scope.replaceAll("_", " ")} / {policy.period}
          </div>
          <div className="mt-1 truncate text-xs text-muted-foreground">
            {policy.scope_id ?? policy.company_id}
          </div>
        </div>
        <StatusBadge value={policy.status} />
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <div>
          {t("budgetLimit")}:{" "}
          <span className="font-medium text-foreground">
            ${formatCost(policy.limit_usd)}
          </span>
        </div>
        <div className="sm:text-right">
          {t("warning")}:{" "}
          <span className="font-medium text-foreground">
            {formatPercent(policy.warning_threshold)}
          </span>
        </div>
        <div className="min-w-0 truncate sm:col-span-2">
          {policy.model_allowlist.length > 0
            ? policy.model_allowlist.join(", ")
            : t("allModels")}
        </div>
        <div className="sm:col-span-2">
          {t("updated")}: {formatDate(policy.updated_at, locale)}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        {canToggle && (
          <Button
            variant="outline"
            size="xs"
            disabled={isMutating}
            onClick={() =>
              void workbench.updateBudgetPolicy(policy.budget_id, {
                status: nextStatus,
              })
            }
          >
            {isMutating ? (
              <Loader2 className="size-3 animate-spin" />
            ) : policy.status === "active" ? (
              <Pause className="size-3" />
            ) : (
              <Play className="size-3" />
            )}
            {policy.status === "active" ? t("pause") : t("activate")}
          </Button>
        )}
        <EditBudgetPolicyDialog policy={policy} workbench={workbench} />
        {policy.status !== "archived" && (
          <Button
            variant="outline"
            size="xs"
            disabled={isMutating}
            onClick={() =>
              void workbench.updateBudgetPolicy(policy.budget_id, {
                status: "archived",
              })
            }
          >
            {isMutating ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <Archive className="size-3" />
            )}
            {t("archive")}
          </Button>
        )}
      </div>
    </div>
  );
}

function GoalList({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const locale = useLocale();

  if (workbench.isLoading) {
    return <ListSkeleton />;
  }

  if (workbench.goals.length === 0) {
    return <EmptyState message={t("noGoals")} />;
  }

  return (
    <div className="space-y-2">
      {workbench.goals.map((goal) => {
        const isActive = goal.goal_id === workbench.activeGoalId;
        const progress = progressValue(goal);
        return (
          <button
            key={goal.goal_id}
            type="button"
            onClick={() => workbench.selectGoal(goal.goal_id)}
            className={cn(
              "group relative w-full overflow-hidden rounded-lg border border-zinc-200/80 bg-white/70 px-3 py-3 text-left shadow-[0_1px_1px_rgba(15,23,42,0.03)] transition hover:border-zinc-300 hover:bg-white dark:border-white/10 dark:bg-white/[0.035] dark:hover:bg-white/[0.06]",
              isActive &&
                "border-zinc-950 bg-white shadow-[0_12px_32px_rgba(15,23,42,0.10)] dark:border-white/40 dark:bg-white/[0.08]",
            )}
          >
            <span
              className={cn(
                "absolute inset-y-3 left-0 w-1 rounded-r-full bg-zinc-300 transition",
                isActive && "bg-zinc-950 dark:bg-white",
              )}
            />
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-[13px] font-semibold leading-5">
                  {goal.title}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {goal.owner_agent_id ?? goal.owner_user_id ?? goal.goal_id}
                </div>
              </div>
              <StatusBadge value={goal.status} />
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>{formatDate(goal.updated_at, locale)}</span>
              <span className="tabular-nums">
                {goal.current_value ?? 0}/{goal.target_value ?? "-"}
              </span>
            </div>
            {progress != null && (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-white/10">
                <div
                  className="h-full rounded-full bg-zinc-950 transition-all dark:bg-white"
                  style={{ width: `${progress}%` }}
                />
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

function WorkQueue({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const locale = useLocale();

  if (workbench.isLoading) {
    return <ListSkeleton />;
  }

  if (workbench.workItems.length === 0) {
    return <EmptyState message={t("noWorkItems")} />;
  }

  return (
    <div className="space-y-2">
      {workbench.workItems.map((workItem) => {
        const isActive = workItem.work_item_id === workbench.activeWorkItemId;
        return (
          <button
            key={workItem.work_item_id}
            type="button"
            onClick={() => workbench.selectWorkItem(workItem.work_item_id)}
            className={cn(
              "group relative w-full overflow-hidden rounded-lg border border-zinc-200/80 bg-white/70 px-3 py-3 text-left shadow-[0_1px_1px_rgba(15,23,42,0.03)] transition hover:border-zinc-300 hover:bg-white dark:border-white/10 dark:bg-white/[0.035] dark:hover:bg-white/[0.06]",
              isActive &&
                "border-zinc-950 bg-white shadow-[0_12px_32px_rgba(15,23,42,0.10)] dark:border-white/40 dark:bg-white/[0.08]",
            )}
          >
            <span
              className={cn(
                "absolute inset-y-3 left-0 w-1 rounded-r-full bg-zinc-300 transition",
                isActive && "bg-zinc-950 dark:bg-white",
              )}
            />
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-[13px] font-semibold leading-5">
                  {workItem.title}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {workItem.owner_agent_id ?? workItem.source}
                </div>
              </div>
              <WorkPriorityBadge priority={workItem.priority} />
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <StatusBadge value={workItem.status} />
                {workItem.approval_required && (
                  <ShieldCheck className="size-3.5 text-amber-600 dark:text-amber-300" />
                )}
              </div>
              <span className="whitespace-nowrap">
                {formatDate(workItem.updated_at, locale)}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function EvidencePanel({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const locale = useLocale();

  if (!workbench.selectedGoal && !workbench.selectedWorkItem) {
    return <EmptyState message={t("noSelection")} />;
  }

  return (
    <Tabs defaultValue="timeline" className="h-full">
      <div className="rounded-lg border border-zinc-200/80 bg-zinc-50/70 p-3 dark:border-white/10 dark:bg-white/[0.035]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {workbench.selectedWorkItem?.title ?? workbench.selectedGoal?.title}
            </div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {workbench.activeRun && <span>{workbench.activeRun.agent_id}</span>}
              {workbench.activeRun && <span>|</span>}
              {workbench.activeRun && (
                <span className="font-mono">{workbench.activeRun.run_id}</span>
              )}
            </div>
          </div>
          {workbench.activeRun && <StatusBadge value={workbench.activeRun.status} />}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <TabsList className="h-9 rounded-lg bg-zinc-100/80 dark:bg-white/10">
          <TabsTrigger value="timeline">{t("timeline")}</TabsTrigger>
          <TabsTrigger value="runs">{t("runs")}</TabsTrigger>
          <TabsTrigger value="approvals">{t("approvals")}</TabsTrigger>
          <TabsTrigger value="decisions">{t("decisions")}</TabsTrigger>
          <TabsTrigger value="artifacts">{t("artifacts")}</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="timeline" className="mt-4">
        {workbench.isEvidenceLoading ? (
          <ListSkeleton />
        ) : (
          <TimelineList items={workbench.timeline} locale={locale} />
        )}
      </TabsContent>

      <TabsContent value="runs" className="mt-4">
        <RunsTable workbench={workbench} locale={locale} />
      </TabsContent>

      <TabsContent value="approvals" className="mt-4">
        <ApprovalList workbench={workbench} locale={locale} />
      </TabsContent>

      <TabsContent value="decisions" className="mt-4">
        <DecisionList decisions={workbench.decisions} locale={locale} />
      </TabsContent>

      <TabsContent value="artifacts" className="mt-4">
        <ArtifactList artifacts={workbench.artifacts} locale={locale} />
      </TabsContent>
    </Tabs>
  );
}

function TimelineList({
  items,
  locale,
}: {
  items: ControlPlaneTimelineItem[];
  locale: string;
}) {
  const t = useTranslations("controlPlane");

  if (items.length === 0) {
    return <EmptyState message={t("noTimeline")} />;
  }

  return (
    <div className="relative space-y-2 pl-3">
      <div className="absolute bottom-3 left-[7px] top-3 w-px bg-zinc-200 dark:bg-white/10" />
      {items.map((item, index) => {
        const title = getString(
          item.data,
          ["title", "action", "status", "artifact_type"],
          item.type,
        );
        const subtitle = getString(
          item.data,
          ["run_id", "target_id", "decision_id", "artifact_id", "approval_id"],
          item.type,
        );

        return (
          <div
            key={`${item.type}-${item.at}-${index}`}
            className="relative rounded-lg border border-zinc-200/80 bg-white/75 px-3 py-3 shadow-[0_1px_1px_rgba(15,23,42,0.03)] dark:border-white/10 dark:bg-white/[0.035]"
          >
            <span
              className={cn(
                "absolute -left-[10px] top-4 size-2.5 rounded-full ring-4 ring-white dark:ring-zinc-950",
                timelineAccentClass[item.type] ?? "bg-zinc-400",
              )}
            />
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-[13px] font-semibold leading-5">
                  {title}
                </div>
                <div className="mt-1 truncate text-xs text-muted-foreground">
                  {subtitle}
                </div>
              </div>
              <StatusBadge value={item.type} />
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              {formatDate(item.at, locale)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RunsTable({
  workbench,
  locale,
}: {
  workbench: Workbench;
  locale: string;
}) {
  const t = useTranslations("controlPlane");

  if (workbench.runs.length === 0) {
    return <EmptyState message={t("noRuns")} />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("run")}</TableHead>
          <TableHead>{t("agent")}</TableHead>
          <TableHead>{t("status")}</TableHead>
          <TableHead>{t("cost")}</TableHead>
          <TableHead>{t("started")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {workbench.runs.map((run) => (
          <RunRow
            key={run.run_id}
            run={run}
            isActive={run.run_id === workbench.activeRunId}
            locale={locale}
            onSelect={workbench.selectRun}
          />
        ))}
      </TableBody>
    </Table>
  );
}

function RunRow({
  run,
  isActive,
  locale,
  onSelect,
}: {
  run: ControlPlaneAgentRun;
  isActive: boolean;
  locale: string;
  onSelect: (runId: string) => void;
}) {
  return (
    <TableRow
      data-state={isActive ? "selected" : undefined}
      className="cursor-pointer data-[state=selected]:bg-zinc-950/[0.04] dark:data-[state=selected]:bg-white/[0.08]"
      onClick={() => onSelect(run.run_id)}
    >
      <TableCell className="max-w-40 truncate font-mono text-xs">
        {run.run_id}
      </TableCell>
      <TableCell>{run.agent_id}</TableCell>
      <TableCell>
        <StatusBadge value={run.status} />
      </TableCell>
      <TableCell className="tabular-nums">${formatCost(run.cost_usd)}</TableCell>
      <TableCell>{formatDate(run.started_at, locale)}</TableCell>
    </TableRow>
  );
}

function DecisionList({
  decisions,
  locale,
}: {
  decisions: ControlPlaneDecision[];
  locale: string;
}) {
  const t = useTranslations("controlPlane");

  if (decisions.length === 0) {
    return <EmptyState message={t("noDecisions")} />;
  }

  return (
    <div className="space-y-2">
      {decisions.map((decision) => (
        <div
          key={decision.decision_id}
          className="rounded-lg border border-zinc-200/80 bg-white/75 px-3 py-3 shadow-[0_1px_1px_rgba(15,23,42,0.03)] dark:border-white/10 dark:bg-white/[0.035]"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-[13px] font-semibold leading-5">
                {decision.title}
              </div>
              <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {decision.rationale}
              </div>
            </div>
            <StatusBadge value={decision.status} />
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>{decision.decided_by ?? decision.decision_id}</span>
            <span>{formatDate(decision.updated_at, locale)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ApprovalList({
  workbench,
  locale,
}: {
  workbench: Workbench;
  locale: string;
}) {
  const t = useTranslations("controlPlane");

  if (workbench.approvals.length === 0) {
    return <EmptyState message={t("noApprovals")} />;
  }

  return (
    <div className="space-y-2">
      {workbench.approvals.map((approval) => (
        <ApprovalItem
          key={approval.approval_id}
          approval={approval}
          locale={locale}
          actionId={workbench.approvalActionId}
          onApprove={workbench.approveApproval}
          onReject={workbench.rejectApproval}
        />
      ))}
    </div>
  );
}

function ApprovalItem({
  approval,
  locale,
  actionId,
  onApprove,
  onReject,
}: {
  approval: ControlPlaneApproval;
  locale: string;
  actionId: string | undefined;
  onApprove: (approvalId: string) => Promise<void>;
  onReject: (approvalId: string) => Promise<void>;
}) {
  const t = useTranslations("controlPlane");
  const isPending = approval.status === "pending";
  const isMutating = actionId === approval.approval_id;

  return (
    <div className="rounded-lg border border-zinc-200/80 bg-white/75 px-3 py-3 shadow-[0_1px_1px_rgba(15,23,42,0.03)] dark:border-white/10 dark:bg-white/[0.035]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold leading-5">
            {approval.proposed_action}
          </div>
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {approval.reason}
          </div>
        </div>
        <StatusBadge value={approval.status} />
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <div className="min-w-0 truncate">{approval.source_agent_id}</div>
        <div className="min-w-0 truncate sm:text-right">
          {formatDate(approval.updated_at, locale)}
        </div>
      </div>

      {isPending && (
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            size="xs"
            disabled={isMutating}
            onClick={() => void onReject(approval.approval_id)}
          >
            {isMutating ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <X className="size-3" />
            )}
            {t("reject")}
          </Button>
          <Button
            size="xs"
            disabled={isMutating}
            onClick={() => void onApprove(approval.approval_id)}
          >
            {isMutating ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <Check className="size-3" />
            )}
            {t("approve")}
          </Button>
        </div>
      )}
    </div>
  );
}

function ArtifactList({
  artifacts,
  locale,
}: {
  artifacts: ControlPlaneArtifact[];
  locale: string;
}) {
  const t = useTranslations("controlPlane");

  if (artifacts.length === 0) {
    return <EmptyState message={t("noArtifacts")} />;
  }

  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => (
        <a
          key={artifact.artifact_id}
          href={artifact.uri}
          className="block rounded-lg border border-zinc-200/80 bg-white/75 px-3 py-3 shadow-[0_1px_1px_rgba(15,23,42,0.03)] transition hover:border-zinc-300 hover:bg-white dark:border-white/10 dark:bg-white/[0.035] dark:hover:bg-white/[0.06]"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-[13px] font-semibold leading-5">
                {artifact.title}
              </div>
              <div className="mt-1 truncate text-xs text-muted-foreground">
                {artifact.uri}
              </div>
            </div>
            <StatusBadge value={artifact.artifact_type} />
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>{artifact.created_by_agent_id ?? artifact.artifact_id}</span>
            <span>{formatDate(artifact.created_at, locale)}</span>
          </div>
        </a>
      ))}
    </div>
  );
}

function EvolutionProposalPanel({ workbench }: { workbench: Workbench }) {
  const t = useTranslations("controlPlane");
  const locale = useLocale();

  return (
    <section className="rounded-lg border border-white/70 bg-white/80 p-4 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/50 dark:shadow-none">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-zinc-950 text-white dark:bg-white dark:text-zinc-950">
            <Sparkles className="size-3.5" />
          </div>
          <h2 className="truncate text-sm font-semibold">
            {t("evolutionProposals")}
          </h2>
        </div>
        <Badge variant="outline" className="h-6 rounded-md px-2 text-[11px]">
          {workbench.evolutionProposals.length}
        </Badge>
      </div>

      {workbench.isEvolutionLoading ? (
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton
              key={index}
              className="h-28 rounded-lg bg-white/60 dark:bg-white/10"
            />
          ))}
        </div>
      ) : workbench.evolutionProposals.length === 0 ? (
        <EmptyState message={t("noEvolutionProposals")} />
      ) : (
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {workbench.evolutionProposals.slice(0, 6).map((proposal) => (
            <EvolutionProposalItem
              key={proposal.proposal_id}
              proposal={proposal}
              locale={locale}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function EvolutionProposalItem({
  proposal,
  locale,
}: {
  proposal: ControlPlaneEvolutionProposal;
  locale: string;
}) {
  const t = useTranslations("controlPlane");

  return (
    <div className="rounded-lg border border-zinc-200/80 bg-white/75 px-3 py-3 shadow-[0_1px_1px_rgba(15,23,42,0.03)] dark:border-white/10 dark:bg-white/[0.035]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold leading-5">
            {proposal.scope}
          </div>
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {proposal.expected_benefit}
          </div>
        </div>
        <Badge variant="outline" className="h-6 rounded-md px-2 text-[11px]">
          {proposal.tier}
        </Badge>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusBadge value={proposal.approval_state} />
        <StatusBadge value={proposal.rollout_state} />
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <div className="min-w-0 truncate">
          {t("tier")}: {proposal.tier}
        </div>
        <div className="min-w-0 truncate sm:text-right">
          {t("updated")}: {formatDate(proposal.updated_at, locale)}
        </div>
      </div>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 4 }).map((_, index) => (
        <Skeleton key={index} className="h-20 rounded-lg bg-white/60 dark:bg-white/10" />
      ))}
    </div>
  );
}

function WorkbenchError({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations("controlPlane");

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-900 shadow-[0_10px_30px_rgba(245,158,11,0.10)] dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
      <div className="flex items-center gap-2">
        <AlertCircle className="size-4" />
        <span>{t("loadError")}</span>
      </div>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw className="size-4" />
        {t("refresh")}
      </Button>
    </div>
  );
}

export function ControlPlaneWorkbenchPage() {
  const t = useTranslations("controlPlane");
  const workbench = useControlPlaneWorkbench();

  const summary = useMemo(
    () => [
      {
        label: t("goals"),
        value: workbench.summary.goalCount,
        icon: Workflow,
      },
      {
        label: t("openWork"),
        value: workbench.summary.openWorkCount,
        icon: GitBranch,
      },
      {
        label: t("pendingApprovals"),
        value: workbench.summary.pendingApprovalCount,
        icon: ShieldCheck,
      },
      {
        label: t("cost"),
        value: `$${formatCost(workbench.summary.costUsd)}`,
        icon: CircleDollarSign,
      },
    ],
    [t, workbench.summary],
  );

  return (
    <div className="-m-6 min-h-[calc(100vh-4rem)] bg-zinc-50 px-4 py-5 sm:px-6 lg:px-8 dark:bg-zinc-950">
      <div className="mx-auto max-w-[1800px] space-y-5">
        <div className="flex flex-col gap-4 rounded-lg border border-white/70 bg-white/80 px-4 py-4 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl sm:px-5 dark:border-white/10 dark:bg-zinc-950/50 dark:shadow-none">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="mb-2 inline-flex items-center gap-2 rounded-md border border-zinc-200/80 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:border-white/10 dark:bg-white/[0.035] dark:text-zinc-300">
                <Sparkles className="size-3.5" />
                {t("title")}
              </div>
              <h1 className="text-[1.7rem] font-semibold leading-tight tracking-normal text-zinc-950 sm:text-[2rem] dark:text-white">
                {workbench.selectedGoal?.title ?? t("title")}
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {workbench.activeRunId && (
                <div className="hidden items-center gap-2 rounded-md border border-zinc-200/80 bg-zinc-50 px-3 py-2 text-xs text-muted-foreground md:flex dark:border-white/10 dark:bg-white/[0.035]">
                  <PanelRightOpen className="size-3.5" />
                  <span className="font-mono">{workbench.activeRunId}</span>
                </div>
              )}
              <Button variant="outline" size="sm" onClick={workbench.refresh}>
                <RefreshCw className="size-4" />
                {t("refresh")}
              </Button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {summary.map((item) => (
              <SummaryMetric
                key={item.label}
                label={item.label}
                value={item.value}
                icon={item.icon}
              />
            ))}
          </div>
        </div>

        {workbench.error && <WorkbenchError onRetry={workbench.refresh} />}

        <BudgetPolicyPanel workbench={workbench} />

        <EvolutionProposalPanel workbench={workbench} />

        <div className="grid gap-4 xl:grid-cols-[minmax(260px,0.85fr)_minmax(300px,1.05fr)_minmax(420px,1.55fr)]">
          <ColumnShell
            title={t("goals")}
            icon={CheckCircle2}
            action={<CreateGoalDialog workbench={workbench} />}
          >
            <GoalList workbench={workbench} />
          </ColumnShell>

          <ColumnShell
            title={t("workQueue")}
            icon={GitBranch}
            action={<CreateWorkItemDialog workbench={workbench} />}
          >
            <WorkQueue workbench={workbench} />
          </ColumnShell>

          <ColumnShell title={t("evidence")} icon={FileText}>
            <EvidencePanel workbench={workbench} />
          </ColumnShell>
        </div>
      </div>
    </div>
  );
}
