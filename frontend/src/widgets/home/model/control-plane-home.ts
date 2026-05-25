import type {
  AgentStatus,
  AgentRuntimeStatus,
  ControlPlaneAgentDefinition,
} from "@/entities/agent";
import type {
  ControlPlaneAgentRun,
  ControlPlaneApproval,
  ControlPlaneWorkItem,
} from "@/entities/control-plane";
import { mapControlPlaneLifecycleStatus } from "@/entities/agent";

const RUNNING_RUN_STATUSES = new Set(["pending", "running"]);
const FAILED_RUN_STATUSES = new Set(["failed", "timed_out"]);
const OPEN_WORK_STATUSES = new Set(["queued", "ready", "running", "blocked", "awaiting_approval"]);
const ATTENTION_WORK_STATUSES = new Set(["blocked", "failed"]);
const ACTION_QUEUE_STATUSES = new Set([...OPEN_WORK_STATUSES, "failed"]);
const WORK_ITEM_ATTENTION_WEIGHT: Record<ControlPlaneWorkItem["status"], number> = {
  failed: 0,
  blocked: 1,
  awaiting_approval: 2,
  running: 3,
  ready: 4,
  queued: 5,
  completed: 6,
  cancelled: 7,
};

export interface HomeCommandCenterSummary {
  runningCount: number;
  attentionCount: number;
  errorCount: number;
  pendingApprovalCount: number;
  agentCount: number;
  openWorkCount: number;
  blockedWorkCount: number;
  approvalWorkCount: number;
  readyWorkCount: number;
  runningWorkCount: number;
  goalLinkedWorkCount: number;
  unassignedWorkCount: number;
  completedRunCount: number;
  failedRunCount: number;
  runCostUsd: number;
  tokenCount: number;
  latestRun: ControlPlaneAgentRun | undefined;
  priorityWorkItem: ControlPlaneWorkItem | undefined;
}

export type HomeOperatorFocusKind =
  | "resolveBlockers"
  | "reviewApprovals"
  | "assignWork"
  | "monitorRuns"
  | "startWork";

export interface HomeOperatorFocus {
  kind: HomeOperatorFocusKind;
  count: number;
  href: "/workflows" | "/approvals" | "/activity" | "/ingest";
  tone: "rose" | "amber" | "sky" | "emerald" | "slate";
}

function latestRun(runs: ControlPlaneAgentRun[]): ControlPlaneAgentRun | undefined {
  return runs.reduce<ControlPlaneAgentRun | undefined>((latest, run) => {
    if (!latest) return run;
    return new Date(run.started_at).getTime() > new Date(latest.started_at).getTime()
      ? run
      : latest;
  }, undefined);
}

function latestTimestamp(
  agent: ControlPlaneAgentDefinition,
  runs: ControlPlaneAgentRun[],
  workItems: ControlPlaneWorkItem[],
): string {
  const timestamps = [
    agent.updated_at,
    ...runs.map((run) => run.completed_at ?? run.started_at),
    ...workItems.map((workItem) => workItem.updated_at),
  ];
  return timestamps.reduce((latest, value) =>
    new Date(value).getTime() > new Date(latest).getTime() ? value : latest,
  );
}

/**
 * Resolves the runtime status of an agent from runtime evidence first,
 * falling back to the catalog lifecycle flag only when no evidence exists.
 *
 * Precedence:
 *   1. An in-flight run (`pending`/`running`) → `running`.
 *   2. A failed run or failed work item        → `error`.
 *   3. Catalog lifecycle (`active` → `idle`, `paused`, `stopped`, ...).
 *
 * This split prevents catalog-enabled (`active`) agents from being shown
 * as live `running` on the dashboard when nothing is actually executing.
 */
function runtimeStatus(
  agent: ControlPlaneAgentDefinition,
  latest: ControlPlaneAgentRun | undefined,
  failedWorkItemCount: number,
): AgentStatus {
  if (latest && RUNNING_RUN_STATUSES.has(latest.status)) return "running";
  if ((latest && FAILED_RUN_STATUSES.has(latest.status)) || failedWorkItemCount > 0) {
    return "error";
  }
  return mapControlPlaneLifecycleStatus(agent.status);
}

function runtimeHealth(status: AgentStatus): number {
  if (status === "running") return 100;
  if (status === "idle" || status === "warning") return 50;
  return 0;
}

export function controlPlaneRuntimeForAgent(
  agent: ControlPlaneAgentDefinition,
  runs: ControlPlaneAgentRun[],
  workItems: ControlPlaneWorkItem[],
): AgentRuntimeStatus {
  const latest = latestRun(runs);
  const failedWorkItems = workItems.filter((workItem) => workItem.status === "failed");
  const failedRunCount = runs.filter((run) => FAILED_RUN_STATUSES.has(run.status)).length;
  const pendingWorkCount = workItems.filter((workItem) =>
    OPEN_WORK_STATUSES.has(workItem.status),
  ).length;
  const status = runtimeStatus(agent, latest, failedWorkItems.length);

  return {
    agent_id: agent.agent_id,
    status,
    health: runtimeHealth(status),
    task_count: runs.length,
    pending_count: pendingWorkCount,
    error_count: failedRunCount + failedWorkItems.length,
    uptime_seconds: 0,
    last_active_at: latestTimestamp(agent, runs, workItems),
  };
}

export function runsForAgent(
  runs: ControlPlaneAgentRun[],
  agentId: string,
): ControlPlaneAgentRun[] {
  return runs.filter((run) => run.agent_id === agentId);
}

export function workItemsForAgent(
  workItems: ControlPlaneWorkItem[],
  agentId: string,
): ControlPlaneWorkItem[] {
  return workItems.filter((workItem) => workItem.owner_agent_id === agentId);
}

export function countOpenWorkItems(workItems: ControlPlaneWorkItem[]): number {
  return workItems.filter((workItem) => OPEN_WORK_STATUSES.has(workItem.status)).length;
}

export function selectPriorityWorkItem(
  workItems: ControlPlaneWorkItem[],
): ControlPlaneWorkItem | undefined {
  return [...workItems]
    .filter((workItem) => ACTION_QUEUE_STATUSES.has(workItem.status))
    .sort((left, right) => {
      const statusDelta =
        WORK_ITEM_ATTENTION_WEIGHT[left.status] - WORK_ITEM_ATTENTION_WEIGHT[right.status];
      if (statusDelta !== 0) return statusDelta;
      return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
    })[0];
}

export function selectHomeOperatorFocus(summary: HomeCommandCenterSummary): HomeOperatorFocus {
  const blockerCount = summary.blockedWorkCount + summary.errorCount;
  if (blockerCount > 0) {
    return {
      kind: "resolveBlockers",
      count: blockerCount,
      href: "/workflows",
      tone: "rose",
    };
  }

  const approvalCount = summary.pendingApprovalCount + summary.approvalWorkCount;
  if (approvalCount > 0) {
    return {
      kind: "reviewApprovals",
      count: approvalCount,
      href: "/approvals",
      tone: "amber",
    };
  }

  if (summary.unassignedWorkCount > 0 || summary.readyWorkCount > 0) {
    return {
      kind: "assignWork",
      count: summary.unassignedWorkCount || summary.readyWorkCount,
      href: "/workflows",
      tone: "sky",
    };
  }

  if (summary.runningWorkCount > 0 || summary.runningCount > 0) {
    return {
      kind: "monitorRuns",
      count: summary.runningWorkCount || summary.runningCount,
      href: "/activity",
      tone: "emerald",
    };
  }

  return {
    kind: "startWork",
    count: 0,
    href: "/ingest",
    tone: "slate",
  };
}

export function summarizeHomeCommandCenter(input: {
  agents: ControlPlaneAgentDefinition[];
  runs: ControlPlaneAgentRun[];
  workItems: ControlPlaneWorkItem[];
  approvals: ControlPlaneApproval[];
}): HomeCommandCenterSummary {
  const runtimes = input.agents.map((agent) =>
    controlPlaneRuntimeForAgent(
      agent,
      runsForAgent(input.runs, agent.agent_id),
      workItemsForAgent(input.workItems, agent.agent_id),
    ),
  );
  const pendingApprovals = input.approvals.filter((approval) => approval.status === "pending");
  const blockedWorkCount = input.workItems.filter((workItem) =>
    ATTENTION_WORK_STATUSES.has(workItem.status),
  ).length;
  const failedRunCount = input.runs.filter((run) => FAILED_RUN_STATUSES.has(run.status)).length;

  return {
    runningCount: runtimes.filter((runtime) => runtime.status === "running").length,
    attentionCount: countOpenWorkItems(input.workItems) + pendingApprovals.length,
    errorCount:
      runtimes.reduce((total, runtime) => total + runtime.error_count, 0) +
      input.workItems.filter((workItem) => workItem.status === "failed" && !workItem.owner_agent_id)
        .length,
    pendingApprovalCount: pendingApprovals.length,
    agentCount: input.agents.length,
    openWorkCount: countOpenWorkItems(input.workItems),
    blockedWorkCount,
    approvalWorkCount: input.workItems.filter((workItem) => workItem.status === "awaiting_approval")
      .length,
    readyWorkCount: input.workItems.filter(
      (workItem) => workItem.status === "ready" || workItem.status === "queued",
    ).length,
    runningWorkCount: input.workItems.filter((workItem) => workItem.status === "running").length,
    goalLinkedWorkCount: input.workItems.filter((workItem) => Boolean(workItem.goal_id)).length,
    unassignedWorkCount: input.workItems.filter(
      (workItem) => !workItem.owner_agent_id && OPEN_WORK_STATUSES.has(workItem.status),
    ).length,
    completedRunCount: input.runs.filter((run) => run.status === "succeeded").length,
    failedRunCount,
    runCostUsd: input.runs.reduce((total, run) => total + run.cost_usd, 0),
    tokenCount: input.runs.reduce((total, run) => total + run.input_tokens + run.output_tokens, 0),
    latestRun: latestRun(input.runs),
    priorityWorkItem: selectPriorityWorkItem(input.workItems),
  };
}
