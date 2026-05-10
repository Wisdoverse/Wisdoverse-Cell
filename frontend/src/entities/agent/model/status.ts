import type { AgentStatus } from "./types";

/**
 * Maps the persisted Control Plane AgentRole lifecycle status to a UI status.
 *
 * The Control Plane stores a *lifecycle* flag on each AgentRole record
 * (`active`, `paused`, `stopped`, ...). It describes whether the role is
 * enabled in the catalog — NOT whether the agent is currently executing
 * a run. Live execution state is derived from `AgentRun` rows.
 *
 * Therefore `active` MUST map to `idle`, never `running`. Returning
 * `running` here would paint every catalog-enabled agent as busy on the
 * home page even when nothing is executing.
 */
export function mapControlPlaneLifecycleStatus(status: string): AgentStatus {
  const normalized = status.trim().toLowerCase();

  if (normalized === "paused") return "paused";
  if (normalized === "error" || normalized === "failed") return "error";
  if (normalized === "stopped" || normalized === "terminated") return "stopped";
  if (normalized === "active" || normalized === "running") return "idle";

  return "idle";
}
