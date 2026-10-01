import useSWR from "swr";

import {
  listControlPlaneGoals,
  getControlPlaneOperatingMetrics,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
  type ControlPlaneGoalFilters,
  type ControlPlaneRunFilters,
  type ControlPlaneWorkItemFilters,
} from "../api/control-plane";
import type {
  ControlPlaneGoalListResponse,
  ControlPlaneOperatingMetrics,
  ControlPlaneRunListResponse,
  ControlPlaneWorkItemListResponse,
} from "./types";

export function useControlPlaneGoals(filters?: ControlPlaneGoalFilters) {
  return useSWR<ControlPlaneGoalListResponse>(["control-plane-goals", filters], () =>
    listControlPlaneGoals(filters),
  );
}

export function useControlPlaneOperatingMetrics(companyId?: string) {
  return useSWR<ControlPlaneOperatingMetrics>(
    ["control-plane-operating-metrics", companyId],
    () => getControlPlaneOperatingMetrics(companyId),
    { refreshInterval: 30_000 },
  );
}

export function useControlPlaneWorkItems(filters?: ControlPlaneWorkItemFilters) {
  return useSWR<ControlPlaneWorkItemListResponse>(["control-plane-work-items", filters], () =>
    listControlPlaneWorkItems(filters),
  );
}

export function useControlPlaneRuns(filters?: ControlPlaneRunFilters) {
  const shouldFetch = Boolean(
    filters?.goal_id || filters?.work_item_id || filters?.agent_id || filters?.trace_id,
  );
  return useSWR<ControlPlaneRunListResponse>(
    shouldFetch ? ["control-plane-runs", filters] : null,
    () => listControlPlaneRuns(filters),
  );
}
