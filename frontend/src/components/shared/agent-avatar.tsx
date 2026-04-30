"use client";

import { getDomainConfig } from "@/lib/registry/domains";
import type { AgentDomain } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface AgentAvatarProps {
  domain: AgentDomain;
  icon: string;
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
        "inline-flex items-center justify-center rounded-xl font-semibold shrink-0",
        sizeClasses[size],
        className
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
