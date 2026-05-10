import type {
  AgentStatus,
  AgentRuntimeStatus,
  ControlPlaneAgentDefinition,
} from "@/entities/agent";
import type {
  ControlPlaneAgentRun,
  ControlPlaneWorkItem,
} from "@/entities/control-plane";
import { mapControlPlaneLifecycleStatus } from "@/entities/agent";

const RUNNING_RUN_STATUSES = new Set(["pending", "running"]);
const FAILED_RUN_STATUSES = new Set(["failed", "timed_out"]);
const OPEN_WORK_STATUSES = new Set([
  "queued",
  "ready",
  "running",
  "blocked",
  "awaiting_approval",
]);

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
