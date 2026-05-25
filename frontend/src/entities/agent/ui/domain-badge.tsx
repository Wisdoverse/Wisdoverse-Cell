"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import { getDomainConfig } from "../model/domains";
import type { AgentDomain } from "../model/types";

interface DomainBadgeProps {
  domain: AgentDomain;
  className?: string;
}

export function DomainBadge({ domain, className }: DomainBadgeProps) {
  const t = useTranslations("agents");
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
      {t(`domainLabels.${config.labelKey}`)}
    </span>
  );
}
