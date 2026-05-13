"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";

import {
  approveControlPlaneApproval,
  createControlPlaneGoal,
  createControlPlaneWorkItem,
  getControlPlaneTimeline,
  listControlPlaneApprovals,
  listControlPlaneArtifacts,
  listControlPlaneBudgetUsage,
  listControlPlaneDecisions,
  listControlPlaneEvolutionProposals,
  listControlPlaneGoals,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
  rejectControlPlaneApproval,
  type ControlPlaneGoalCreateRequest,
  type ControlPlaneGoalFilters,
  type ControlPlaneWorkItemCreateRequest,
  type ControlPlaneRunFilters,
  type ControlPlaneWorkItemFilters,
} from "../api/control-plane";
import type {
  ControlPlaneAgentRun,
  ControlPlaneApprovalListResponse,
  ControlPlaneArtifactListResponse,
  ControlPlaneBudgetUsageListResponse,
  ControlPlaneDecisionListResponse,
  ControlPlaneEvolutionProposalListResponse,
  ControlPlaneGoalListResponse,
  ControlPlaneTimelineResponse,
  ControlPlaneWorkbenchSummary,
  ControlPlaneWorkItem,
  ControlPlaneWorkItemListResponse,
  WorkItemStatus,
} from "./types";

const OPEN_WORK_STATUSES: WorkItemStatus[] = [
  "queued",
  "ready",
  "running",
  "blocked",
  "awaiting_approval",
  "failed",
];

function isOpenWorkItem(workItem: ControlPlaneWorkItem): boolean {
  return OPEN_WORK_STATUSES.includes(workItem.status);
}

export function pickLatestRun(
  runs: ControlPlaneAgentRun[],
  selectedRunId?: string,
): ControlPlaneAgentRun | undefined {
  if (selectedRunId) {
    const selected = runs.find((run) => run.run_id === selectedRunId);
    if (selected) return selected;
  }
  return runs[0];
}

export function summarizeControlPlaneWorkbench(input: {
  goals: ControlPlaneGoalListResponse | undefined;
  workItems: ControlPlaneWorkItemListResponse | undefined;
  approvals: ControlPlaneApprovalListResponse | undefined;
  budgetUsage: ControlPlaneBudgetUsageListResponse | undefined;
}): ControlPlaneWorkbenchSummary {
  const workItems = input.workItems?.work_items ?? [];
  const approvals = input.approvals?.approvals ?? [];
  const usage = input.budgetUsage?.usage ?? [];

  return {
    goalCount: input.goals?.total ?? input.goals?.goals.length ?? 0,
    openWorkCount: workItems.filter(isOpenWorkItem).length,
    pendingApprovalCount: approvals.filter(
      (approval) => approval.status === "pending",
    ).length,
    costUsd: usage.reduce((total, item) => total + item.cost_usd, 0),
  };
}

export function useControlPlaneGoals(filters?: ControlPlaneGoalFilters) {
  return useSWR<ControlPlaneGoalListResponse>(["control-plane-goals", filters], () =>
    listControlPlaneGoals(filters),
  );
}

export function useControlPlaneWorkItems(
  filters?: ControlPlaneWorkItemFilters,
) {
  return useSWR<ControlPlaneWorkItemListResponse>(
    ["control-plane-work-items", filters],
    () => listControlPlaneWorkItems(filters),
  );
}

export function useControlPlaneRuns(filters?: ControlPlaneRunFilters) {
  const shouldFetch = Boolean(
    filters?.goal_id || filters?.work_item_id || filters?.agent_id || filters?.trace_id,
  );
  return useSWR(
    shouldFetch ? ["control-plane-runs", filters] : null,
    () => listControlPlaneRuns(filters),
  );
}

export function useControlPlaneWorkbench() {
  const [selectedGoalId, setSelectedGoalId] = useState<string>();
  const [selectedWorkItemId, setSelectedWorkItemId] = useState<string>();
  const [selectedRunId, setSelectedRunId] = useState<string>();
  const [approvalActionId, setApprovalActionId] = useState<string>();
  const [goalActionId, setGoalActionId] = useState<string>();
  const [workItemActionId, setWorkItemActionId] = useState<string>();

  const goalsQuery = useControlPlaneGoals({ limit: 100 });
  const goals = useMemo(() => goalsQuery.data?.goals ?? [], [goalsQuery.data]);
  const activeGoalId = selectedGoalId ?? goals[0]?.goal_id;
  const selectedGoal = goals.find((goal) => goal.goal_id === activeGoalId);

  const workItemsQuery = useControlPlaneWorkItems({
    goal_id: activeGoalId,
    limit: 100,
  });
  const workItems = useMemo(
    () => workItemsQuery.data?.work_items ?? [],
    [workItemsQuery.data],
  );
  const activeWorkItemId = selectedWorkItemId ?? workItems[0]?.work_item_id;
  const selectedWorkItem = workItems.find(
    (workItem) => workItem.work_item_id === activeWorkItemId,
  );

  const runsQuery = useControlPlaneRuns({
    goal_id: activeGoalId,
    work_item_id: activeWorkItemId,
    limit: 50,
  });
  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data]);
  const activeRun = pickLatestRun(runs, selectedRunId);
  const activeRunId = activeRun?.run_id;

  const decisionsQuery = useSWR<ControlPlaneDecisionListResponse>(
    activeGoalId || activeWorkItemId
      ? [
          "control-plane-decisions",
          activeGoalId,
          activeWorkItemId,
          activeRunId,
        ]
      : null,
    () =>
      listControlPlaneDecisions({
        goal_id: activeGoalId,
        work_item_id: activeWorkItemId,
        run_id: activeRunId,
        limit: 50,
      }),
  );

  const artifactsQuery = useSWR<ControlPlaneArtifactListResponse>(
    activeGoalId || activeWorkItemId
      ? [
          "control-plane-artifacts",
          activeGoalId,
          activeWorkItemId,
          activeRunId,
        ]
      : null,
    () =>
      listControlPlaneArtifacts({
        goal_id: activeGoalId,
        work_item_id: activeWorkItemId,
        run_id: activeRunId,
        limit: 50,
      }),
  );

  const approvalsQuery = useSWR<ControlPlaneApprovalListResponse>(
    activeRunId ? ["control-plane-approvals", activeRunId] : null,
    () => listControlPlaneApprovals({ run_id: activeRunId, limit: 50 }),
  );

  const budgetUsageQuery = useSWR<ControlPlaneBudgetUsageListResponse>(
    activeRunId ? ["control-plane-budget-usage", activeRunId] : null,
    () => listControlPlaneBudgetUsage({ run_id: activeRunId, limit: 50 }),
  );

  const timelineQuery = useSWR<ControlPlaneTimelineResponse>(
    activeRunId ? ["control-plane-timeline", activeRunId] : null,
    () => getControlPlaneTimeline({ run_id: activeRunId, limit: 100 }),
  );

  const evolutionProposalsQuery =
    useSWR<ControlPlaneEvolutionProposalListResponse>(
      ["control-plane-evolution-proposals", { limit: 25 }],
      () => listControlPlaneEvolutionProposals({ limit: 25 }),
    );

  const selectGoal = useCallback((goalId: string) => {
    setSelectedGoalId(goalId);
    setSelectedWorkItemId(undefined);
    setSelectedRunId(undefined);
  }, []);

  const selectWorkItem = useCallback((workItemId: string) => {
    setSelectedWorkItemId(workItemId);
    setSelectedRunId(undefined);
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([
      goalsQuery.mutate(),
      workItemsQuery.mutate(),
      runsQuery.mutate(),
      decisionsQuery.mutate(),
      artifactsQuery.mutate(),
      approvalsQuery.mutate(),
      budgetUsageQuery.mutate(),
      timelineQuery.mutate(),
      evolutionProposalsQuery.mutate(),
    ]);
  }, [
    approvalsQuery,
    artifactsQuery,
    budgetUsageQuery,
    decisionsQuery,
    evolutionProposalsQuery,
    goalsQuery,
    runsQuery,
    timelineQuery,
    workItemsQuery,
  ]);

  const refresh = useCallback(() => {
    void refreshAll();
  }, [refreshAll]);

  const approveApproval = useCallback(
    async (approvalId: string) => {
      setApprovalActionId(approvalId);
      try {
        await approveControlPlaneApproval(approvalId, {
          resolved_by: "human:operator",
        });
        await refreshAll();
      } finally {
        setApprovalActionId(undefined);
      }
    },
    [refreshAll],
  );

  const rejectApproval = useCallback(
    async (approvalId: string) => {
      setApprovalActionId(approvalId);
      try {
        await rejectControlPlaneApproval(approvalId, {
          resolved_by: "human:operator",
        });
        await refreshAll();
      } finally {
        setApprovalActionId(undefined);
      }
    },
    [refreshAll],
  );

  const createGoal = useCallback(
    async (payload: ControlPlaneGoalCreateRequest) => {
      setGoalActionId("create");
      try {
        const goal = await createControlPlaneGoal({
          status: "active",
          created_by: "human:operator",
          ...payload,
        });
        setSelectedGoalId(goal.goal_id);
        setSelectedWorkItemId(undefined);
        setSelectedRunId(undefined);
        await refreshAll();
      } finally {
        setGoalActionId(undefined);
      }
    },
    [refreshAll],
  );

  const createWorkItem = useCallback(
    async (payload: ControlPlaneWorkItemCreateRequest) => {
      setWorkItemActionId("create");
      try {
        const workItem = await createControlPlaneWorkItem({
          status: "ready",
          priority: "medium",
          source: "manual",
          created_by: "human:operator",
          ...payload,
          goal_id: payload.goal_id ?? activeGoalId,
        });
        setSelectedWorkItemId(workItem.work_item_id);
        setSelectedRunId(undefined);
        await refreshAll();
      } finally {
        setWorkItemActionId(undefined);
      }
    },
    [activeGoalId, refreshAll],
  );

  const summary = summarizeControlPlaneWorkbench({
    goals: goalsQuery.data,
    workItems: workItemsQuery.data,
    approvals: approvalsQuery.data,
    budgetUsage: budgetUsageQuery.data,
  });

  return {
    goals,
    workItems,
    runs,
    decisions: decisionsQuery.data?.decisions ?? [],
    artifacts: artifactsQuery.data?.artifacts ?? [],
    evolutionProposals:
      evolutionProposalsQuery.data?.evolution_proposals ?? [],
    approvals: approvalsQuery.data?.approvals ?? [],
    budgetUsage: budgetUsageQuery.data?.usage ?? [],
    timeline: timelineQuery.data?.timeline ?? [],
    selectedGoal,
    selectedWorkItem,
    activeRun,
    activeGoalId,
    activeWorkItemId,
    activeRunId,
    selectedRunId,
    selectGoal,
    selectWorkItem,
    selectRun: setSelectedRunId,
    approveApproval,
    rejectApproval,
    createGoal,
    createWorkItem,
    refresh,
    summary,
    approvalActionId,
    goalActionId,
    workItemActionId,
    isLoading: goalsQuery.isLoading || workItemsQuery.isLoading,
    isEvidenceLoading:
      runsQuery.isLoading ||
      decisionsQuery.isLoading ||
      artifactsQuery.isLoading ||
      approvalsQuery.isLoading ||
      budgetUsageQuery.isLoading ||
      timelineQuery.isLoading,
    isEvolutionLoading: evolutionProposalsQuery.isLoading,
    error:
      goalsQuery.error ||
      workItemsQuery.error ||
      runsQuery.error ||
      decisionsQuery.error ||
      artifactsQuery.error ||
      approvalsQuery.error ||
      budgetUsageQuery.error ||
      timelineQuery.error ||
      evolutionProposalsQuery.error,
  };
}

export type ControlPlaneWorkbenchState = ReturnType<
  typeof useControlPlaneWorkbench
>;
