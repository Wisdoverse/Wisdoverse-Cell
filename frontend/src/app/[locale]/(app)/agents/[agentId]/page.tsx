"use client";

import { useParams } from "next/navigation";

import { AgentDetailPage } from "@/widgets/agent-detail";

export default function AgentDetailRoute() {
  const params = useParams<{ agentId: string }>();
  return <AgentDetailPage agentId={params.agentId} />;
}
