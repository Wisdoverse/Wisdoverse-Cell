import type { AgentDomain } from "@/lib/api/types";
import { getDomainConfig } from "@/lib/registry/domains";
import { cn } from "@/lib/utils";

interface DomainBadgeProps {
  domain: AgentDomain;
  className?: string;
}

export function DomainBadge({ domain, className }: DomainBadgeProps) {
  const config = getDomainConfig(domain);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        className
      )}
      style={{
        backgroundColor: config.colorLight,
        color: config.color,
      }}
    >
      {config.label}
    </span>
  );
}
