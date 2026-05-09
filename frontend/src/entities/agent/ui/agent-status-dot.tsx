"use client";

import { cn } from "@/lib/utils";
import type { AgentStatus } from "../model/types";

interface AgentStatusDotProps {
  status: AgentStatus;
  size?: "sm" | "md";
  className?: string;
}

const statusStyles: Record<AgentStatus, string> = {
  running: "bg-[var(--status-running)]",
  idle: "bg-muted-foreground",
  paused: "bg-[var(--status-paused)]",
  warning: "bg-[var(--status-warning)]",
  error: "bg-[var(--status-error)]",
  stopped: "bg-muted-foreground/50",
};

export function AgentStatusDot({
  status,
  size = "md",
  className,
}: AgentStatusDotProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-full",
        size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5",
        statusStyles[status],
        className,
      )}
    />
  );
}
