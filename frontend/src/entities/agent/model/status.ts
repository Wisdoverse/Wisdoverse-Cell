import type { AgentStatus } from "./types";

export function mapControlPlaneAgentStatus(status: string): AgentStatus {
  const normalized = status.trim().toLowerCase();

  if (normalized === "active" || normalized === "running") return "running";
  if (normalized === "paused") return "paused";
  if (normalized === "error" || normalized === "failed") return "error";
  if (normalized === "stopped" || normalized === "terminated") return "stopped";

  return "idle";
}
