import { cn } from "@/lib/utils";
import type { AgentStatus } from "../model/types";

interface AgentStatusDotProps {
  status: AgentStatus;
  size?: "sm" | "md";
  className?: string;
}

const statusStyles: Record<AgentStatus, string> = {
  running: "bg-green-500 animate-pulse",
  idle: "bg-gray-400",
  paused: "bg-amber-500",
  warning: "bg-amber-500",
  error: "bg-red-500",
  stopped: "border-2 border-gray-400 bg-transparent",
};

const sizeStyles = {
  sm: "h-2 w-2",
  md: "h-2.5 w-2.5",
};

export function AgentStatusDot({
  status,
  size = "md",
  className,
}: AgentStatusDotProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-full shrink-0",
        sizeStyles[size],
        statusStyles[status],
        className
      )}
      aria-label={status}
    />
  );
}
