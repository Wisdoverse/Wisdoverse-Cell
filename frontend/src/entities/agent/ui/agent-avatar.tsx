"use client";

import { cn } from "@/lib/utils";
import { getDomainConfig } from "../model/domains";
import type { AgentDomain } from "../model/types";

interface AgentAvatarProps {
  domain: AgentDomain;
  shortName: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-16 w-16 text-lg",
};

export function AgentAvatar({
  domain,
  shortName,
  size = "md",
  className,
}: AgentAvatarProps) {
  const config = getDomainConfig(domain);

  return (
    <div
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg font-semibold",
        sizeClasses[size],
        className,
      )}
      style={{
        backgroundColor: config.colorLight,
        color: config.color,
      }}
    >
      {shortName}
    </div>
  );
}
