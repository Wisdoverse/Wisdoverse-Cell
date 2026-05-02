"use client";

import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { wakeControlPlaneAgent } from "@/entities/agent";
import { Button } from "@/components/ui/button";

interface AgentWakeupButtonProps {
  agentId: string;
  onWoken?: () => void;
}

export function AgentWakeupButton({ agentId, onWoken }: AgentWakeupButtonProps) {
  const t = useTranslations("agents");
  const tc = useTranslations("common");
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    try {
      const result = await wakeControlPlaneAgent(agentId, {
        actor_id: "frontend",
        input: {},
      });
      toast.success(t("wakeSuccess", { runId: result.run.run_id }));
      onWoken?.();
    } catch {
      toast.error(tc("error"));
    } finally {
      setPending(false);
    }
  }

  return (
    <Button onClick={onClick} disabled={pending}>
      {pending ? <Loader2 className="animate-spin" /> : <Play />}
      {t("wakeAgent")}
    </Button>
  );
}
