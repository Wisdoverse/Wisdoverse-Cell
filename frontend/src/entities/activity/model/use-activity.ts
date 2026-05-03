import useSWR from "swr";

import { getActivity } from "@/lib/api/activity";
import type { ActivityListResponse } from "@/lib/api/types";

export function useActivity(filters?: {
  agent_id?: string;
  domain?: string;
  limit?: number;
}) {
  return useSWR<ActivityListResponse>(
    ["activity", filters],
    () => getActivity(filters),
    { refreshInterval: 15000 },
  );
}
