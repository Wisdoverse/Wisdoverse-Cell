import useSWR from "swr";
import { getStats, getEnhancedStats } from "@/lib/api/admin";

export function useStats() {
  return useSWR("stats", getStats, { refreshInterval: 30000 });
}

export function useEnhancedStats() {
  return useSWR("enhanced-stats", getEnhancedStats, { refreshInterval: 30000 });
}
