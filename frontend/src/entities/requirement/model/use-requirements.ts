import useSWR from "swr";

import { getRequirement, listRequirements } from "@/lib/api/requirements";
import type { RequirementFilters } from "@/lib/api/types";

export function useRequirements(filters: RequirementFilters = {}) {
  const key = ["requirements", JSON.stringify(filters)];
  return useSWR(key, () => listRequirements(filters));
}

export function useRequirement(id: string | null) {
  return useSWR(id ? ["requirement", id] : null, () => getRequirement(id!));
}
