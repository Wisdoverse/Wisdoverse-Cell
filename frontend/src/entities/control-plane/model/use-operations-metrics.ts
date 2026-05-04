import useSWR from "swr";

import {
  getCircuitBreaker,
  getEnhancedStats,
  getHealthReady,
  getLLMUsage,
  getStats,
} from "@/lib/api/admin";

export function useStats() {
  return useSWR("stats", getStats, { refreshInterval: 30000 });
}

export function useEnhancedStats() {
  return useSWR("enhanced-stats", getEnhancedStats, { refreshInterval: 30000 });
}

export function useLLMUsage(date?: string) {
  return useSWR(["llm-usage", date], () => getLLMUsage(date), {
    refreshInterval: 10000,
  });
}

export function useCircuitBreaker() {
  return useSWR("circuit-breaker", getCircuitBreaker, {
    refreshInterval: 10000,
  });
}

export function useHealthReady() {
  return useSWR("health-ready", getHealthReady, { refreshInterval: 10000 });
}
