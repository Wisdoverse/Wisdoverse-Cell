"use client";

import { useState } from "react";
import { Loader2, Play, RotateCcw, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import {
  updateControlPlaneAgentStatus,
  wakeControlPlaneAgent,
} from "@/entities/agent";
import { Button } from "@/shared/ui/button";

type AgentControlAction = "start" | "restart" | "stop";

interface AgentControlActionsProps {
  agentId: string;
  status?: string;
  onChanged?: () => Promise<void> | void;
}

function isStopped(status: string | undefined): boolean {
  const normalized = status?.toLowerCase();
  return normalized === "paused" || normalized === "terminated";
}

export function AgentControlActions({
  agentId,
  status,
  onChanged,
}: AgentControlActionsProps) {
  const t = useTranslations("agents");
  const tc = useTranslations("common");
  const [pendingAction, setPendingAction] = useState<AgentControlAction | null>(
    null,
  );

  async function refresh() {
    await Promise.resolve(onChanged?.());
  }

  async function wake(action: "start" | "restart") {
    await updateControlPlaneAgentStatus(agentId, {
      status: "active",
      actor_id: "human:operator",
    });
    const result = await wakeControlPlaneAgent(agentId, {
      actor_id: "human:operator",
      input: { action },
    });
    toast.success(t(`${action}Success`, { runId: result.run.run_id }));
  }

  async function update(action: AgentControlAction) {
    setPendingAction(action);
    try {
      if (action === "stop") {
        await updateControlPlaneAgentStatus(agentId, {
          status: "paused",
          actor_id: "human:operator",
        });
        toast.success(t("stopSuccess"));
      } else {
        await wake(action);
      }
      await refresh();
    } catch (error) {
      console.error(`[agent-control] ${action} failed`, error);
      toast.error(tc("error"));
    } finally {
      setPendingAction(null);
    }
  }

  const pending = pendingAction !== null;
  const stopped = isStopped(status);

  return (
    <div className="flex flex-wrap justify-end gap-2">
      <Button
        size="sm"
        onClick={() => update("start")}
        disabled={pending || !stopped}
      >
        {pendingAction === "start" ? (
          <Loader2 className="animate-spin" />
        ) : (
          <Play />
        )}
        {t("startAgent")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => update("restart")}
        disabled={pending}
      >
        {pendingAction === "restart" ? (
          <Loader2 className="animate-spin" />
        ) : (
          <RotateCcw />
        )}
        {t("restartAgent")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => update("stop")}
        disabled={pending || stopped}
      >
        {pendingAction === "stop" ? (
          <Loader2 className="animate-spin" />
        ) : (
          <Square />
        )}
        {t("stopAgent")}
      </Button>
    </div>
  );
}
