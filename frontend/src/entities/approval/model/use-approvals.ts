import useSWR from "swr";

import { getApprovals } from "@/lib/api/approvals";
import type { ApprovalListResponse } from "@/lib/api/types";

export function useApprovals(filters?: {
  type?: string;
  status?: string;
}) {
  return useSWR<ApprovalListResponse>(
    ["approvals", filters],
    () => getApprovals(filters),
    { refreshInterval: 15000 },
  );
}
