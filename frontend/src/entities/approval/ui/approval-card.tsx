"use client";

import type { ApprovalRequest } from "@/lib/api/types";
import { AgentDisplayAvatar, AGENT_REGISTRY, DomainBadge } from "@/entities/agent";
import { Button } from "@/shared/ui/button";
import { Check, X, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ApprovalCardProps {
  approval: ApprovalRequest;
  onApprove?: () => void;
  onReject?: () => void;
  onAsk?: () => void;
  className?: string;
}

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function ApprovalCard({
  approval,
  onApprove,
  onReject,
  onAsk,
  className,
}: ApprovalCardProps) {
  const agentMeta = AGENT_REGISTRY[approval.source_agent_id];

  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-4 space-y-3",
        approval.urgency === "urgent" && "border-red-300 dark:border-red-800",
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {agentMeta && (
            <AgentDisplayAvatar
              domain={agentMeta.domain}
              icon={agentMeta.icon}
              shortName={agentMeta.shortName}
              size="sm"
            />
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate">{approval.title}</div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {agentMeta && <span>{agentMeta.name}</span>}
              {agentMeta && <DomainBadge domain={agentMeta.domain} />}
            </div>
          </div>
        </div>
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {formatTimeAgo(approval.created_at)}
        </span>
      </div>

      <p className="text-sm text-muted-foreground">{approval.summary}</p>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={onApprove} className="gap-1" aria-label="Approve">
          <Check className="h-3.5 w-3.5" />
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onReject}
          className="gap-1 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950"
          aria-label="Reject"
        >
          <X className="h-3.5 w-3.5" />
          Reject
        </Button>
        {onAsk && (
          <Button size="sm" variant="ghost" onClick={onAsk} className="gap-1" aria-label="Ask">
            <MessageCircle className="h-3.5 w-3.5" />
            Ask
          </Button>
        )}
      </div>
    </div>
  );
}
